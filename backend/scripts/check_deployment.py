"""Read-only deployment configuration check; never a real-service acceptance gate.

Print fixed check identifiers and booleans only. Do not connect to a database,
contact a provider, write files, generate keys, or echo configuration values.
"""

import argparse
import base64
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from app.core.config import Settings


# Vercel documents these framework-prefixed public metadata variables.
VERCEL_PUBLIC_VARIABLES = {
    'NEXT_PUBLIC_VERCEL_ENV',
    'NEXT_PUBLIC_VERCEL_TARGET_ENV',
    'NEXT_PUBLIC_VERCEL_URL',
    'NEXT_PUBLIC_VERCEL_BRANCH_URL',
    'NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL',
    'NEXT_PUBLIC_VERCEL_HASH_SALT',
    'NEXT_PUBLIC_VERCEL_GIT_PROVIDER',
    'NEXT_PUBLIC_VERCEL_GIT_REPO_SLUG',
    'NEXT_PUBLIC_VERCEL_GIT_REPO_OWNER',
    'NEXT_PUBLIC_VERCEL_GIT_REPO_ID',
    'NEXT_PUBLIC_VERCEL_GIT_COMMIT_REF',
    'NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA',
    'NEXT_PUBLIC_VERCEL_GIT_COMMIT_MESSAGE',
    'NEXT_PUBLIC_VERCEL_GIT_COMMIT_AUTHOR_LOGIN',
    'NEXT_PUBLIC_VERCEL_GIT_COMMIT_AUTHOR_NAME',
    'NEXT_PUBLIC_VERCEL_GIT_PULL_REQUEST_ID',
}


MANUAL_ACCEPTANCE = [
    'supabase_two_user_auth_and_isolation',
    'own_provider_video_to_answer_and_citations',
    'api_worker_shared_durable_files_and_vectors',
    'database_migrations_backup_and_key_recovery',
    'worker_restart_and_data_persistence',
    'production_ingress_limits_and_monitoring',
    'api_cors_auth_redirects_and_readiness',
]


def public_origin(value: str) -> str | None:
    if not value or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        if (
            parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ('', '/') or parsed.port not in (None, 443)
            or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', host)
            or host.rsplit('.', 1)[-1].isdigit()
            or host.endswith(('.localhost', '.local', '.internal', '.invalid'))
        ):
            return None
        return f'https://{host}'
    except ValueError:
        return None


def public_supabase_key(value: str) -> bool:
    """Check key *shape* only; do not authenticate or validate a JWT signature."""
    if len(value) > 8192:
        return False
    if value.startswith('sb_publishable_'):
        return len(value) > len('sb_publishable_') + 10 and bool(re.fullmatch(r'[A-Za-z0-9_-]+', value))
    try:
        _, payload, _ = value.split('.')
        decoded = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return isinstance(decoded, dict) and decoded.get('role') == 'anon'
    except (ValueError, TypeError, UnicodeError):
        return False


def check_configuration(config: 'Settings', frontend: Mapping[str, str]) -> dict:
    from cryptography.fernet import Fernet
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    checks: dict[str, bool] = {}
    checks['production_mode'] = config.is_production
    checks['supported_vector_backend'] = config.vector_store_backend in ('chroma', 'pgvector')
    checks['supported_file_backend'] = config.file_storage_backend.lower() in ('local', 'supabase')
    if config.file_storage_backend.lower() == 'supabase':
        from app.services.object_storage.supabase import SupabaseObjectStore
        try:
            store = SupabaseObjectStore(config.supabase_url, config.supabase_storage_service_key, config.supabase_storage_bucket)
            store.close()  # Shape validation only; no network request.
            checks['storage_server_configuration'] = True
        except Exception:
            checks['storage_server_configuration'] = False
    checks['supabase_auth_mode'] = config.auth_mode.lower() == 'supabase'
    supabase = public_origin(config.supabase_url)
    checks['backend_supabase_https_origin'] = supabase is not None
    checks['backend_supabase_public_key_shape'] = public_supabase_key(config.supabase_anon_key)
    try:
        Fernet(config.user_api_key_encryption_key.encode())
        checks['encryption_key_format'] = True
    except (ValueError, TypeError, UnicodeError):
        checks['encryption_key_format'] = False
    checks['explicit_migrations'] = not config.auto_create_database_tables
    try:
        database = make_url(config.database_url)
        checks['postgresql_psycopg_connection'] = (
            database.drivername == 'postgresql+psycopg' and bool(database.host and database.database and database.username)
            and database.host not in ('localhost', '127.0.0.1', 'postgres', '::1')
        )
        checks['database_tls_required'] = database.query.get('sslmode') in ('require', 'verify-ca', 'verify-full')
    except (ValueError, TypeError, ArgumentError):
        checks['postgresql_psycopg_connection'] = False
        checks['database_tls_required'] = False
    site = public_origin(frontend.get('NEXT_PUBLIC_APP_URL', ''))
    checks['frontend_https_origin'] = site is not None
    origins = [public_origin(origin) for origin in config.cors_origins]
    checks['cors_exact_https_origins'] = (
        bool(origins) and all(origins) and site is not None and site in origins
        and all(raw == normalized for raw, normalized in zip(config.cors_origins, origins, strict=True))
    )
    frontend_supabase = public_origin(frontend.get('NEXT_PUBLIC_SUPABASE_URL', ''))
    checks['same_supabase_project'] = supabase is not None and frontend_supabase == supabase
    checks['frontend_supabase_public_key_shape'] = public_supabase_key(frontend.get('NEXT_PUBLIC_SUPABASE_ANON_KEY', ''))
    checks['frontend_public_variables_allowlist'] = all(
        key in ('NEXT_PUBLIC_APP_URL', 'NEXT_PUBLIC_API_BASE_URL', 'NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY')
        for key in frontend if key.startswith('NEXT_PUBLIC_') and key not in VERCEL_PUBLIC_VARIABLES
    )
    api_base = frontend.get('NEXT_PUBLIC_API_BASE_URL', '')
    try:
        api = urlsplit(api_base)
        checks['frontend_api_https_and_prefix'] = (
            public_origin(f'{api.scheme}://{api.netloc}') is not None
            and api.path == config.api_v1_prefix and not api.query and not api.fragment
        )
    except ValueError:
        checks['frontend_api_https_and_prefix'] = False
    internal_api = frontend.get('INTERNAL_API_BASE_URL', '')
    checks['server_api_matches_browser'] = not internal_api or internal_api == api_base
    checks['absolute_storage_paths'] = all(
        Path(getattr(config, f'{kind}_storage_dir')).is_absolute()
        for kind in ('video', 'audio', 'transcript', 'note')
    ) and (config.vector_store_backend != 'chroma' or config.chroma_mode != 'embedded' or Path(config.chroma_persist_dir).is_absolute())
    checks['disk_free_space_floor_enabled'] = config.min_media_free_space_mb > 0
    warnings = []
    if config.asr_provider == 'disabled':
        warnings.append('asr_disabled_subtitles_only')
    if config.embedding_provider == 'local_hash':
        warnings.append('hash_retrieval_quality_not_accepted')
    return {
        'status': 'configuration_passed' if all(checks.values()) else 'blocked',
        'ready_for_public_users': False,
        'checks': checks,
        'warnings': warnings,
        'manual_acceptance_required': MANUAL_ACCEPTANCE,
        'network_checks_performed': False,
        'writes_performed': False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-env-file', type=Path, help='Read planned frontend variables from a local file; process env wins')
    args = parser.parse_args(argv)
    try:
        # Defer Settings import so even a Pydantic error cannot echo secret inputs.
        from app.core.config import settings
        from dotenv import dotenv_values

        frontend = {}
        if args.frontend_env_file:
            frontend = {key: value for key, value in dotenv_values(args.frontend_env_file, interpolate=False).items() if value is not None}
            if not args.frontend_env_file.is_file():
                raise ValueError('Missing environment file')
        frontend.update(os.environ)
        result = check_configuration(settings, frontend)
    except Exception:
        print(json.dumps({'status': 'blocked', 'reason': 'configuration_unreadable_or_invalid', 'ready_for_public_users': False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status'] == 'configuration_passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
