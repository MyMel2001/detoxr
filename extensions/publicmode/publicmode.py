from flask import request, make_response, redirect
import config
import json
import urllib.parse

DOMAIN = "settings.config"

COOKIE_NAME = "macproxy_settings"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year

# Default settings keys
SETTING_KEYS = [
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "BLUESKY_PDS_URL",
    "ZIP_CODE",
    "GITHUB_USERS",
    "SAMANTHA_API_BASE_URL",
    "SAMANTHA_API_KEY",
    "SAMANTHA_MODEL",
    "SAMANTHA_WEBSIM_API_BASE_URL",
    "SAMANTHA_WEBSIM_API_KEY",
    "SAMANTHA_WEBSIM_MODEL",
]


def _serialize_github_users(user_list):
    """Convert a list of GitHub usernames to a comma-separated string."""
    if isinstance(user_list, list):
        return ", ".join(user_list)
    return str(user_list) if user_list else ""


def _deserialize_github_users(user_string):
    """Convert a comma-separated string of GitHub usernames to a list."""
    if isinstance(user_string, list):
        return user_string
    if not user_string or not user_string.strip():
        return []
    return [u.strip() for u in user_string.split(",") if u.strip()]


def get_settings_from_cookie():
    """Read settings from the request cookie."""
    cookie_value = request.cookies.get(COOKIE_NAME, "")
    if not cookie_value:
        return {}

    try:
        decoded = urllib.parse.unquote(cookie_value)
        return json.loads(decoded)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[PublicMode] Error decoding cookie: {e}")
        return {}


def apply_settings_to_config(settings):
    """Patch config module with the given settings dict."""
    if settings.get("BLUESKY_HANDLE"):
        config.BLUESKY_HANDLE = settings["BLUESKY_HANDLE"]
    if settings.get("BLUESKY_APP_PASSWORD"):
        config.BLUESKY_APP_PASSWORD = settings["BLUESKY_APP_PASSWORD"]
    if settings.get("BLUESKY_PDS_URL"):
        config.BLUESKY_PDS_URL = settings["BLUESKY_PDS_URL"]
    if settings.get("ZIP_CODE"):
        config.ZIP_CODE = settings["ZIP_CODE"]
    if settings.get("GITHUB_USERS"):
        config.GITHUB_USERS = _deserialize_github_users(settings["GITHUB_USERS"])
    if settings.get("SAMANTHA_API_BASE_URL"):
        config.SAMANTHA_API_BASE_URL = settings["SAMANTHA_API_BASE_URL"]
    if settings.get("SAMANTHA_API_KEY"):
        config.SAMANTHA_API_KEY = settings["SAMANTHA_API_KEY"]
    if settings.get("SAMANTHA_MODEL"):
        config.SAMANTHA_MODEL = settings["SAMANTHA_MODEL"]
    if settings.get("SAMANTHA_WEBSIM_API_BASE_URL"):
        config.SAMANTHA_WEBSIM_API_BASE_URL = settings["SAMANTHA_WEBSIM_API_BASE_URL"]
    if settings.get("SAMANTHA_WEBSIM_API_KEY"):
        config.SAMANTHA_WEBSIM_API_KEY = settings["SAMANTHA_WEBSIM_API_KEY"]
    if settings.get("SAMANTHA_WEBSIM_MODEL"):
        config.SAMANTHA_WEBSIM_MODEL = settings["SAMANTHA_WEBSIM_MODEL"]


def apply_cookie_settings():
    """Called before each request to apply per-user cookie settings to config."""
    settings = get_settings_from_cookie()
    if settings:
        apply_settings_to_config(settings)


def build_cookie_value(settings):
    """Build a URL-encoded JSON cookie value from a settings dict."""
    # Only store non-empty values
    to_store = {k: v for k, v in settings.items() if v}
    return urllib.parse.quote(json.dumps(to_store))


SETTINGS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
	<title>Public Mode Settings</title>
</head>
<body>
	<center>
		<h1><font size="7"><h4>Public Mode<br>Settings</h4></font></h1>
		<p>Configure your personal preferences below.<br>
		These settings are stored in a cookie on your browser<br>
		and are used by extensions like Weather, GitHub,<br>
		and Golden Years.</p>
	</center>
	<hr>
	<form method="post">
		<p><strong>Bluesky Handle:</strong><br>
		<input type="text" name="bluesky_handle" value="{{ bluesky_handle }}" size="40"><br>
		<small>Your Bluesky handle<br>
		(e.g. your-handle.bsky.social)</small></p>
		<p><strong>Bluesky App Password:</strong><br>
		<input type="password" name="bluesky_app_password" value="{{ bluesky_app_password }}" size="40"><br>
		<small>Your Bluesky app password<br>
		(not your main account password)</small></p>
		<p><strong>Bluesky PDS URL:</strong><br>
		<input type="text" name="pds_url" value="{{ pds_url }}" size="40"><br>
		<small>Your Personal Data Server endpoint<br>
		(e.g. https://bsky.social)</small></p>
		<p><strong>Zip Code:</strong><br>
		<input type="text" name="zip_code" value="{{ zip_code }}" size="10"><br>
		<small>Your US zip code for weather forecasts</small></p>
		<p><strong>GitHub Users:</strong><br>
		<input type="text" name="github_users" value="{{ github_users }}" size="50"><br>
		<small>Comma-separated GitHub usernames<br>
		whose repos will appear on github.com</small></p>
		<p><strong>Samantha API Base URL:</strong><br>
		<input type="text" name="samantha_api_base_url" value="{{ samantha_api_base_url }}" size="40"><br>
		<small>OpenAI-compatible endpoint for Samantha</small></p>
		<p><strong>Samantha API Key:</strong><br>
		<input type="password" name="samantha_api_key" value="{{ samantha_api_key }}" size="40"><br>
		<small>Your Samantha API key</small></p>
		<p><strong>Samantha Model:</strong><br>
		<input type="text" name="samantha_model" value="{{ samantha_model }}" size="40"><br>
		<small>Model name for Samantha</small></p>
		<p><strong>Samantha WebSimulator API Base URL:</strong><br>
		<input type="text" name="samantha_websim_api_base_url" value="{{ samantha_websim_api_base_url }}" size="40"><br>
		<small>OpenAI-compatible endpoint for Samantha WebSimulator</small></p>
		<p><strong>Samantha WebSimulator API Key:</strong><br>
		<input type="password" name="samantha_websim_api_key" value="{{ samantha_websim_api_key }}" size="40"><br>
		<small>Your Samantha WebSimulator API key</small></p>
		<p><strong>Samantha WebSimulator Model:</strong><br>
		<input type="text" name="samantha_websim_model" value="{{ samantha_websim_model }}" size="40"><br>
		<small>Model name for Samantha WebSimulator</small></p>
		<hr>
		<center>
			<input type="submit" name="action" value="Save Settings">
			&nbsp;&nbsp;
			<input type="submit" name="action" value="Clear Settings">
		</center>
	</form>
	{% if message %}
	<center><p><strong>{{ message }}</strong></p></center>
	{% endif %}
	<hr>
	<center>
		<p><small>Public Mode &mdash; personal settings for Macproxy</small></p>
	</center>
</body>
</html>
"""


def handle_request(req):
    settings = get_settings_from_cookie()

    message = ""

    if req.method == 'POST':
        action = req.form.get('action')

        if action == 'Save Settings':
            new_settings = {
                "BLUESKY_HANDLE": req.form.get('bluesky_handle', '').strip(),
                "BLUESKY_APP_PASSWORD": req.form.get('bluesky_app_password', '').strip(),
                "BLUESKY_PDS_URL": req.form.get('pds_url', '').strip(),
                "ZIP_CODE": req.form.get('zip_code', '').strip(),
                "GITHUB_USERS": req.form.get('github_users', '').strip(),
                "SAMANTHA_API_BASE_URL": req.form.get('samantha_api_base_url', '').strip(),
                "SAMANTHA_API_KEY": req.form.get('samantha_api_key', '').strip(),
                "SAMANTHA_MODEL": req.form.get('samantha_model', '').strip(),
                "SAMANTHA_WEBSIM_API_BASE_URL": req.form.get('samantha_websim_api_base_url', '').strip(),
                "SAMANTHA_WEBSIM_API_KEY": req.form.get('samantha_websim_api_key', '').strip(),
                "SAMANTHA_WEBSIM_MODEL": req.form.get('samantha_websim_model', '').strip(),
            }
            cookie_value = build_cookie_value(new_settings)
            resp = make_response(redirect("http://settings.config/"))
            resp.set_cookie(
                COOKIE_NAME,
                value=cookie_value,
                max_age=COOKIE_MAX_AGE,
                path="/",
            )
            return resp

        elif action == 'Clear Settings':
            resp = make_response(redirect("http://settings.config/"))
            resp.set_cookie(COOKIE_NAME, value="", max_age=0, path="/")
            return resp

    # Pre-fill from cookie, falling back to config.py defaults
    pds_url = settings.get("BLUESKY_PDS_URL", getattr(config, 'BLUESKY_PDS_URL', ''))
    bluesky_handle = settings.get("BLUESKY_HANDLE", getattr(config, 'BLUESKY_HANDLE', ''))
    bluesky_app_password = settings.get("BLUESKY_APP_PASSWORD", getattr(config, 'BLUESKY_APP_PASSWORD', ''))
    zip_code = settings.get("ZIP_CODE", str(getattr(config, 'ZIP_CODE', '')))
    github_users = settings.get("GITHUB_USERS", _serialize_github_users(getattr(config, 'GITHUB_USERS', [])))
    samantha_api_base_url = settings.get("SAMANTHA_API_BASE_URL", getattr(config, 'SAMANTHA_API_BASE_URL', ''))
    samantha_api_key = settings.get("SAMANTHA_API_KEY", getattr(config, 'SAMANTHA_API_KEY', ''))
    samantha_model = settings.get("SAMANTHA_MODEL", getattr(config, 'SAMANTHA_MODEL', ''))
    samantha_websim_api_base_url = settings.get("SAMANTHA_WEBSIM_API_BASE_URL", getattr(config, 'SAMANTHA_WEBSIM_API_BASE_URL', ''))
    samantha_websim_api_key = settings.get("SAMANTHA_WEBSIM_API_KEY", getattr(config, 'SAMANTHA_WEBSIM_API_KEY', ''))
    samantha_websim_model = settings.get("SAMANTHA_WEBSIM_MODEL", getattr(config, 'SAMANTHA_WEBSIM_MODEL', ''))

    from flask import render_template_string
    return render_template_string(
        SETTINGS_TEMPLATE,
        pds_url=pds_url,
        bluesky_handle=bluesky_handle,
        bluesky_app_password=bluesky_app_password,
        zip_code=zip_code,
        github_users=github_users,
        samantha_api_base_url=samantha_api_base_url,
        samantha_api_key=samantha_api_key,
        samantha_model=samantha_model,
        samantha_websim_api_base_url=samantha_websim_api_base_url,
        samantha_websim_api_key=samantha_websim_api_key,
        samantha_websim_model=samantha_websim_model,
        message=message
    )
