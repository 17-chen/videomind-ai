"""Read-only PostgreSQL restore comparison; row contents and digests stay private."""

from contextlib import ExitStack
import hashlib

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


REQUIRED_TABLES = ('users', 'videos', 'transcripts', 'summaries', 'embeddings',
                   'ai_settings', 'video_tasks', 'request_windows')
OPTIONAL_TABLES = ('alembic_version', 'alembic_version_pgvector', 'alembic_version_objects',
                   'vm_vector_chunks', 'vm_storage_objects')


class VerificationUnavailable(Exception):
    pass


class BudgetExceeded(Exception):
    pass


def _shape(connection, table):
    if connection.scalar(text('SELECT row_security_active(CAST(:table AS regclass))'), {'table': f'public.{table}'}):
        # A filtered view can make two incomplete copies appear equal.
        raise VerificationUnavailable()
    columns = connection.execute(text('''
        SELECT column_name, udt_schema, udt_name, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale,
               datetime_precision, collation_schema, collation_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position
    '''), {'table': table}).all()
    primary_key = inspect(connection).get_pk_constraint(table, schema='public')['constrained_columns']
    if not primary_key:
        raise VerificationUnavailable()
    return columns, primary_key


def _digest(connection, table, primary_key, budget, max_rows, max_bytes):
    quote = connection.dialect.identifier_preparer.quote
    order = ', '.join(quote(name) for name in primary_key)
    statement = text(f'SELECT row_to_json(t)::text FROM public.{quote(table)} AS t ORDER BY {order}')
    digest = hashlib.sha256()
    count = 0
    # Server-side cursor bounds client buffering. One oversized row can still
    # arrive before its byte budget is checked; this is not a memory hard cap.
    with connection.execute(statement, execution_options={'stream_results': True}).yield_per(100) as rows:
        for row in rows:
            encoded = row[0].encode('utf-8')
            budget['rows_read'] += 1
            budget['bytes_read'] += len(encoded)
            if budget['rows_read'] > max_rows or budget['bytes_read'] > max_bytes:
                raise BudgetExceeded()
            # Hash PostgreSQL's exact rendering. Parsing JSON through Python
            # floats could hide changes to high-precision numeric values.
            digest.update(len(encoded).to_bytes(8, 'big'))
            digest.update(encoded)
            count += 1
    return count, digest.digest()


def compare_database_restore(source: Engine, restored: Engine, *, max_rows=100000, max_bytes=67108864) -> dict:
    """Compare an existing isolated restore. Never create/restore/drop a database.

    Both connections use read-only repeatable-read views. Their snapshots are
    independent: stop writes and use the same recovery point before comparing.
    """
    report = {'status': 'unavailable', 'reason': None, 'tables': {},
              'rows_read': 0, 'bytes_read': 0, 'writes_performed': False}
    try:
        if max_rows < 1 or max_bytes < 1:
            raise VerificationUnavailable()
        if source.dialect.name != 'postgresql' or restored.dialect.name != 'postgresql':
            raise VerificationUnavailable()
        # Separate database names deliberately reject same-name deployments,
        # even on different hosts. Read-only comparison must not "verify" itself.
        source_name, restored_name = source.url.database, restored.url.database
        if not source_name or not restored_name or source_name == restored_name or not restored_name.startswith('vm_restore_'):
            report['reason'] = 'target_not_isolated'
            return report
        with ExitStack() as stack:
            connections = []
            for engine in (source, restored):
                connection = stack.enter_context(engine.connect().execution_options(isolation_level='REPEATABLE READ'))
                stack.enter_context(connection.begin())
                connection.execute(text('SET TRANSACTION READ ONLY'))
                connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                connection.execute(text("SET LOCAL statement_timeout = '15000ms'"))
                connection.execute(text("SET LOCAL lock_timeout = '3000ms'"))
                connections.append(connection)
            source_db, restored_db = [c.scalar(text('SELECT current_database()')) for c in connections]
            if source_db != source_name or restored_db != restored_name or source_db == restored_db:
                report['reason'] = 'target_not_isolated'
                return report
            inventories = [set(inspect(c).get_table_names(schema='public')) for c in connections]
            for name in (*REQUIRED_TABLES, *OPTIONAL_TABLES):
                presence = [name in inventory for inventory in inventories]
                if not any(presence) and name in OPTIONAL_TABLES:
                    report['tables'][name] = {'status': 'not_present'}
                    continue
                if not all(presence):
                    report['tables'][name] = {'status': 'mismatch', 'reason': 'missing_table'}
                    continue
                shapes = [_shape(c, name) for c in connections]
                if shapes[0] != shapes[1]:
                    report['tables'][name] = {'status': 'mismatch', 'reason': 'schema_difference'}
                    continue
                fingerprints = [_digest(c, name, shapes[0][1], report, max_rows, max_bytes) for c in connections]
                report['tables'][name] = {
                    'status': 'matched' if fingerprints[0] == fingerprints[1] else 'mismatch',
                    'source_rows': fingerprints[0][0], 'restored_rows': fingerprints[1][0],
                }
            report['status'] = 'mismatch' if any(v['status'] == 'mismatch' for v in report['tables'].values()) else 'matched'
    except BudgetExceeded:
        report.update(status='inconclusive', reason='read_budget_exceeded')
    except Exception:
        # Never expose SQL, row values, hashes, addresses or exception messages.
        report.update(status='unavailable', reason='database_verification_failed')
    return report
