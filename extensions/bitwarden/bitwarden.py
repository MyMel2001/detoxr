"""
Password Vault CSV Reader extension.

Lets you load an exported password manager CSV (Bitwarden "unencrypted" format,
or any CSV with a compatible header) from a URL and browse/search the entries
from your classic web browser.

The CSV is fetched from a URL you supply on the control page, parsed into a
table, and displayed in a retro-compatible (HTML 3.2) interface.

The CSV URL is stored in a per-browser cookie (like the publicmode settings),
so it persists between sessions without any server-side state.

Bitwarden CSV columns (typical):
    folder,favorite,type,name,notes,fields,reprompt,
    login_uri,login_username,login_password,login_totp

Common columns used here:
    name, login_uri / url, login_username / username, login_password / password,
    notes, folder, totp
"""

from flask import request, make_response
import csv
import io
import requests
import html

# Browse to this domain in your browser (via the proxy) to open the reader.
DOMAIN = "bitwarden.passwords"

# Cookie that holds the CSV URL for this browser (a per-user config setting).
COOKIE_NAME = "bitwarden_csv_url"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


def _get_csv_url():
	"""Read the CSV URL from the request cookie (config setting)."""
	return request.cookies.get(COOKIE_NAME, "")


def _parse_csv(text):
	"""Parse CSV text into (headers, rows). Handles a quoted header row."""
	reader = csv.reader(io.StringIO(text))
	try:
		header_row = next(reader)
	except StopIteration:
		return [], []

	headers = [h.strip() for h in header_row]
	rows = []
	for row in reader:
		if not row:
			continue
		# Pad short rows so indexes line up with headers.
		row = row + [''] * (len(headers) - len(row))
		record = {}
		for i, h in enumerate(headers):
			record[h] = row[i] if i < len(row) else ''
		rows.append(record)
	return headers, rows


def _load_csv(url):
	"""Fetch and parse a CSV from a URL. Returns (entries, headers, error)."""
	try:
		resp = requests.get(url, timeout=30)
		resp.raise_for_status()
		text = resp.text
	except Exception as e:
		return [], [], f"Could not fetch CSV: {str(e)}"

	try:
		headers, rows = _parse_csv(text)
	except Exception as e:
		return [], [], f"Could not parse CSV: {str(e)}"

	if not headers:
		return [], [], "The file is empty or not a valid CSV."

	return rows, headers, None


def _field(record, *candidates):
	"""Return the first non-empty value among candidate column names."""
	for c in candidates:
		val = record.get(c, '')
		if val:
			return val
	return ''


def _render_page(csv_url, entries, headers, error, query=None):
	"""Render a retro-compatible HTML 3.2 page."""
	# Filter by query string if present.
	shown = entries
	if query:
		q = query.lower()
		shown = [r for r in entries
				 if any(q in str(v).lower() for v in r.values())]

	out = []
	out.append('<html>\n<head>\n<title>Vault CSV Reader</title>\n</head>\n<body>\n')
	out.append('<center><h1>Vault CSV Reader</h1></center>\n')
	out.append('<hr>\n')

	# Control / load form.
	out.append('<form method="post" action="/">\n')
	out.append('CSV URL: <input type="text" name="csv_url" size="60" value="%s"><br>\n'
			   % html.escape(csv_url or '', quote=True))
	out.append('<input type="submit" name="action" value="Load CSV">\n')
	out.append('<input type="submit" name="action" value="Clear URL">\n')
	out.append('</form>\n')

	if error:
		out.append('<p><font color="red"><b>%s</b></font></p>\n' % html.escape(error))

	# Search form (GET) if data is loaded.
	if headers and not error:
		out.append('<hr>\n')
		out.append('<form method="get" action="/">\n')
		out.append('Search: <input type="text" name="q" size="30" value="%s">\n'
				   % html.escape(query or '', quote=True))
		out.append('<input type="submit" value="Search">\n')
		out.append('</form>\n')
		out.append('<p>%d of %d entries shown. Column headers detected: %s</p>\n'
				   % (len(shown), len(entries), html.escape(', '.join(headers))))

		out.append('<hr>\n<table border="1" cellpadding="4">\n')
		out.append('<tr><th>Name</th><th>Username</th><th>Password</th>'
				   '<th>URL</th><th>Folder</th><th>Notes</th><th>2FA (TOTP)</th></tr>\n')
		for r in shown:
			name = _field(r, 'name', 'title', 'item')
			user = _field(r, 'username', 'login_username', 'user')
			pwd = _field(r, 'password', 'login_password', 'pass')
			uri = _field(r, 'url', 'login_uri', 'uri', 'website')
			folder = _field(r, 'folder', 'collection')
			notes = _field(r, 'notes', 'comment')
			totp = _field(r, 'totp', 'login_totp')

			if uri:
				uri_cell = '<a href="%s">%s</a>' % (html.escape(uri), html.escape(uri))
			else:
				uri_cell = ''

			# Render the password in a text field (HTML 3.2-friendly, copyable).
			pwd_cell = ('<input type="text" name="reveal" value="%s">' % html.escape(pwd)) \
				if pwd else ''

			out.append('<tr>')
			out.append('<td>%s</td>' % html.escape(name))
			out.append('<td>%s</td>' % html.escape(user))
			out.append('<td>%s</td>' % pwd_cell)
			out.append('<td>%s</td>' % uri_cell)
			out.append('<td>%s</td>' % html.escape(folder))
			out.append('<td>%s</td>' % html.escape(notes))
			out.append('<td>%s</td>' % html.escape(totp))
			out.append('</tr>\n')
		out.append('</table>\n')

	out.append('</body>\n</html>\n')
	return ''.join(out)


def handle_request(req):
	# The URL is a per-browser config setting stored in a cookie.
	csv_url = _get_csv_url()
	error = None
	query = None
	entries = []
	headers = []

	if req.method == 'POST':
		action = req.form.get('action')

		if action == 'Clear URL':
			# Clear the cookie setting.
			html_page = _render_page('', [], [], None, None)
			resp = make_response(html_page, 200)
			resp.set_cookie(COOKIE_NAME, value="", max_age=0, path="/")
			return resp

		# Load URL: persist it to the cookie, then fetch + parse.
		new_url = (req.form.get('csv_url') or '').strip()
		csv_url = new_url
		entries, headers, error = _load_csv(csv_url)

		html_page = _render_page(csv_url, entries, headers, error, None)
		resp = make_response(html_page, 200)
		if new_url:
			resp.set_cookie(COOKIE_NAME, value=new_url, max_age=COOKIE_MAX_AGE, path="/")
		return resp

	# GET: reload from the cookie URL if one is configured.
	query = req.args.get('q') or None
	if csv_url:
		entries, headers, error = _load_csv(csv_url)

	return _render_page(csv_url, entries, headers, error, query), 200
