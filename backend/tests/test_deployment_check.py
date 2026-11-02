import json
import os
import subprocess
import sys

from cryptography.fernet import Fernet
import pytest

from app.core.config import Settings
from scripts.check_deployment import check_configuration, public_origin, public_supabase_key


@pytest.fixture
def deployment_config():
    config = Settings(
        _env_file=None, app_env='production', auth_mode='supabase',
        supabase_url='https://project.example.com', supabase_anon_key='sb_publishable_synthetic_public_key',
        user_api_key_encryption_key=Fernet.generate_key().decode(), auto_create_database_tables=False,
        database_url='postgresql+psycopg://synthetic:synthetic@db.example.com/app?sslmode=require',
        backend_cors_origins='https://app.example.com',
    )
    frontend = {
        'NEXT_PUBLIC_APP_URL': 'https://app.example.com',
        'NEXT_PUBLIC_VERCEL_URL': 'synthetic-preview.vercel.app',
        'NEXT_PUBLIC_API_BASE_URL': 'https://api.example.com/api/v1',
        'NEXT_PUBLIC_SUPABASE_URL': 'https://project.example.com',
        'NEXT_PUBLIC_SUPABASE_ANON_KEY': 'sb_publishable_synthetic_public_key',
    }
    return config, frontend


def test_passing_configuration_never_claims_service_acceptance_or_outputs_values(deployment_config):
    config, frontend = deployment_config
    result = check_configuration(config, frontend)
    assert result['status'] == 'configuration_passed'
    assert result['ready_for_public_users'] is False
    assert result['network_checks_performed'] is False
    assert result['writes_performed'] is False
    assert 'api_worker_shared_durable_files_and_vectors' in result['manual_acceptance_required']
    assert all(result['checks'].values())
    for value in [config.database_url, config.supabase_anon_key, config.user_api_key_encryption_key, *frontend.values()]:
        assert value not in json.dumps(result)


@pytest.mark.parametrize(('field', 'value', 'failed_check'), [
    ('app_env', 'local', 'production_mode'),
    ('auth_mode', 'demo', 'supabase_auth_mode'),
    ('supabase_anon_key', 'sb_secret_do_not_expose', 'backend_supabase_public_key_shape'),
    ('supabase_anon_key', 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.synthetic', 'backend_supabase_public_key_shape'),
    ('user_api_key_encryption_key', 'invalid-master-secret', 'encryption_key_format'),
    ('auto_create_database_tables', True, 'explicit_migrations'),
    ('database_url', 'sqlite:///local.db', 'postgresql_psycopg_connection'),
    ('database_url', 'invalid-private-url', 'postgresql_psycopg_connection'),
    ('database_url', 'postgresql+psycopg://test:private@db.example.com/app?sslmode=disable', 'database_tls_required'),
    ('backend_cors_origins', '*', 'cors_exact_https_origins'),
    ('backend_cors_origins', 'https://*.example.com', 'cors_exact_https_origins'),
    ('backend_cors_origins', 'https://other.example.com', 'cors_exact_https_origins'),
    ('backend_cors_origins', 'https://app.example.com/', 'cors_exact_https_origins'),
    ('video_storage_dir', 'relative/videos', 'absolute_storage_paths'),
])
def test_unsafe_backend_configuration_is_blocked(deployment_config, field, value, failed_check):
    config, frontend = deployment_config
    result = check_configuration(config.model_copy(update={field: value}), frontend)
    assert result['status'] == 'blocked'
    assert result['checks'][failed_check] is False
    if isinstance(value, str):
        assert value not in json.dumps(result)


@pytest.mark.parametrize(('field', 'value', 'failed_check'), [
    ('NEXT_PUBLIC_API_BASE_URL', 'http://localhost:8000/api/v1', 'frontend_api_https_and_prefix'),
    ('NEXT_PUBLIC_API_BASE_URL', 'https://private:password@api.example.com/api/v1', 'frontend_api_https_and_prefix'),
    ('NEXT_PUBLIC_SUPABASE_URL', 'https://other.example.com', 'same_supabase_project'),
    ('INTERNAL_API_BASE_URL', 'http://backend:8000/api/v1', 'server_api_matches_browser'),
    ('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'sb_secret_private_key', 'frontend_supabase_public_key_shape'),
    ('NEXT_PUBLIC_OWNER_API_KEY', 'must-not-be-published', 'frontend_public_variables_allowlist'),
])
def test_cross_service_mismatch_or_private_frontend_key_is_blocked(deployment_config, field, value, failed_check):
    config, frontend = deployment_config
    result = check_configuration(config, {**frontend, field: value})
    assert result['status'] == 'blocked'
    assert result['checks'][failed_check] is False
    assert value not in json.dumps(result)


@pytest.mark.parametrize('origin', [
    'http://app.example.com', 'https://localhost', 'https://127.0.0.1', 'https://127.1',
    'https://app.example.com/path', 'https://app.example.com?private=secret',
    'https://name:password@app.example.com', 'https://app.example.com\n',
    'https://*.example.com', 'https://[bad', 'https://app.example.com:bad',
])
def test_public_origin_rejects_local_wildcard_credentials_and_invalid_urls(origin):
    assert public_origin(origin) is None


def test_legacy_anon_shape_is_accepted_but_not_a_signature_verification():
    assert public_supabase_key('eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.synthetic')
    assert not public_supabase_key('not-a-key')


def test_invalid_settings_cli_never_leaks_pydantic_input_values():
    env = {**os.environ, 'MAX_MEDIA_STAGE_MB': 'private-sentinel-value'}
    result = subprocess.run([sys.executable, '-m', 'scripts.check_deployment'], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout)['reason'] == 'configuration_unreadable_or_invalid'
    assert not result.stderr
    assert 'private-sentinel-value' not in result.stdout
