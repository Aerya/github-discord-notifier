from app.security import validate_discord_webhook

def test_discord_url_validation():
    assert validate_discord_webhook('https://discord.com/api/webhooks/123/token')
    assert not validate_discord_webhook('http://discord.com/api/webhooks/123/token')
    assert not validate_discord_webhook('https://evil.example/api/webhooks/123/token')
