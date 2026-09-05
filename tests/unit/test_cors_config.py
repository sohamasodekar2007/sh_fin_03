from apps.api.config import Settings


def test_production_vercel_origin_is_allowed_by_default():
    settings = Settings(cors_origins="http://localhost:3000")

    assert "https://sh-fin-03.vercel.app" in settings.cors_origin_list


def test_cors_origins_include_app_base_and_webauthn_without_trailing_slash():
    settings = Settings(
        cors_origins="http://localhost:3000, 'https://admin.example.com/' ",
        app_base_url='"https://frontend.example.com/"',
        webauthn_origin="https://passkeys.example.com/",
    )

    assert "https://admin.example.com" in settings.cors_origin_list
    assert "https://frontend.example.com" in settings.cors_origin_list
    assert "https://passkeys.example.com" in settings.cors_origin_list
    assert all(not origin.endswith("/") for origin in settings.cors_origin_list)
    assert all(not origin.startswith(("'", '"')) for origin in settings.cors_origin_list)


def test_cors_origin_regex_allows_vercel_deployments():
    settings = Settings()

    assert settings.cors_origin_regex == r"https://.*\.vercel\.app"
