# Standard library imports
import copy
import hashlib
import html
import re
from urllib.parse import quote, urljoin

# Third-party imports
from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter
from flask import current_app, url_for

# First-party imports
from utils.image_utils import fetch_and_cache_image
from utils.system_utils import load_preset

# Get config
config = load_preset()


class URLAwareHTMLFormatter(HTMLFormatter):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def escape(self, string):
		"""
		Escape special characters in the given string or list of strings.
		"""
		if isinstance(string, list):
			return [html.escape(str(item), quote=True) for item in string]
		elif string is None:
			return ''
		else:
			return html.escape(str(string), quote=True)

	def attributes(self, tag):
		for key, val in tag.attrs.items():
			if key in ['href', 'src']:  # Don't escape URL attributes
				yield key, val
			else:
				yield key, self.escape(val)

def transcode_content(content):
	"""
	Convert HTTPS to HTTP in CSS or JavaScript content
	"""
	if isinstance(content, bytes):
		content = content.decode('utf-8', errors='replace')
		
	# Simple pattern to match URLs in both CSS and JS
	patterns = [
		(r"""url\(['"]?(https://[^)'"]+)['"]?\)""", r"url(\1)"),  # CSS url()
		(r'"https://', '"http://'),  # Double-quoted URLs
		(r"'https://", "'http://"),  # Single-quoted URLs
		(r"https://", "http://"),    # Unquoted URLs
	]
	
	for pattern, replacement in patterns:
		content = re.sub(pattern, 
						lambda m: replacement.replace(r"\1", 
						m.group(1).replace("https://", "http://") if len(m.groups()) > 0 else ""),
						content)
	
	return content.encode('utf-8')

def transcode_html(html, url=None, whitelisted_domains=None, simplify_html=False,
				  tags_to_unwrap=None, tags_to_strip=None, attributes_to_strip=None,
				  convert_characters=False, conversion_table=None,
				  frontend_base_url=None):
	"""
	Uses BeautifulSoup to transcode payloads of the text/html content type
	"""

	if isinstance(html, bytes):
		html = html.decode("utf-8", errors="replace")

	# Handle character conversion regardless of whitelist status
	if convert_characters:
		for key, replacement in conversion_table.items():
			if isinstance(replacement, bytes):
				replacement = replacement.decode("utf-8")
			html = html.replace(key, replacement)

	# The html5lib parser is required in order to preserve case-sensitivity of
	# tags. Using html.parser will corrupt SVGs and possibly other XML tags.
	soup = BeautifulSoup(html, "html5lib")

	# Contents of <pre> tags should always use HTML entities
	for tag in soup.find_all(['pre']):
		tag.replace_with(str(tag))

	if frontend_base_url and url:
		for tag in soup(['a', 'area', 'link', 'iframe', 'img', 'input', 'script']):
			for attr in ['href', 'src']:
				if attr in tag.attrs:
					target = tag[attr]
					if not target.startswith(('#', 'mailto:', 'tel:', 'data:', 'javascript:')):
						tag[attr] = f"{frontend_base_url}?url={quote(urljoin(url, target), safe='')}"
		for tag in soup.find_all('form'):
			action = tag.get('action', url)
			tag['action'] = frontend_base_url
			hidden = soup.new_tag('input', attrs={'type': 'hidden', 'name': 'url', 'value': urljoin(url, action)})
			tag.insert(0, hidden)

	# Always convert HTTPS to HTTP regardless of whitelist status
	for tag in soup(['link', 'script', 'img', 'a', 'iframe']):
		# Handle src attributes
		if 'src' in tag.attrs:
			if tag['src'].startswith('https://'):
				tag['src'] = tag['src'].replace('https://', 'http://')
			elif tag['src'].startswith('//'):  # Handle protocol-relative URLs
				tag['src'] = 'http:' + tag['src']

		# Handle href attributes
		if 'href' in tag.attrs:
			if tag['href'].startswith('https://'):
				tag['href'] = tag['href'].replace('https://', 'http://')
			elif tag['href'].startswith('//'):  # Handle protocol-relative URLs
				tag['href'] = 'http:' + tag['href']

	# Check if domain is whitelisted
	is_whitelisted = False
	if url:
		from urllib.parse import urlparse
		domain = urlparse(url).netloc
		is_whitelisted = any(domain.endswith(whitelisted) for whitelisted in whitelisted_domains)

	# Only perform tag/attribute stripping if the domain is not whitelisted and SIMPLIFY_HTML is True
	if simplify_html and not is_whitelisted:
		for tag in soup(tags_to_unwrap):
			tag.unwrap()
		for tag in soup(tags_to_strip):
			tag.decompose()
		for tag in soup():
			for attr in attributes_to_strip:
				if attr in tag.attrs:
					del tag[attr]

	# Keep extension redirects inside Web frontend. Without this, NewNet actions
	# redirect to a proxy-relative URL and leave its extension routing context.
	for tag in soup.find_all('meta', attrs={'http-equiv': 'refresh'}):
		if 'content' not in tag.attrs:
			continue
		if frontend_base_url and url:
			match = re.match(r'^(\s*\d+(?:\.\d+)?\s*;\s*url\s*=\s*)(.*)$', tag['content'], re.IGNORECASE)
			if match:
				tag['content'] = f"{match.group(1)}{frontend_base_url}?url={quote(urljoin(url, match.group(2).strip()), safe='')}"
		elif 'https://' in tag['content']:
			tag['content'] = tag['content'].replace('https://', 'http://')

	# Always handle CSS with inline URLs
	for tag in soup.find_all(['style', 'link']):
		if tag.string:
			tag.string = tag.string.replace('https://', 'http://')

	# Handle inline SVGs - first pass
	# if any SVG has a child element containing <use href="#value"> or
	# <use xlink:href="#value"> then we need to find _another_ SVG on the page
	# with a child element containing <symbol id="value">, and replace the
	# contents of the first element with the contents of the second. If the
	# symbol tag defines a viewport, that viewport needs to be copied to the
	# parent of the use tag (which should be a svg tag)
	for use_tag in soup.find_all(['use']):
		attrs = use_tag.attrs
		if 'href' in attrs:
			attr = 'href'
		elif 'xlink:href' in attrs:
			attr = 'xlink:href'
		symbol_tag = soup.find("symbol", {"id": use_tag[attr][1:]})
		if 'viewBox' in symbol_tag.attrs and use_tag.parent.name == 'svg' and 'viewBox' not in use_tag.parent.attrs:
			use_tag.parent["viewBox"] = symbol_tag["viewBox"]
		symbol_tag_copy = copy.copy(symbol_tag)
		use_tag.replace_with(symbol_tag_copy)
		symbol_tag_copy.unwrap()

	# Handle inline SVGs - second pass
	# Fetch, cache, and convert them - then replace the inline <svg> tag with
	# an <img> tag whose src attribute points to this proxy _itself_.
	for tag in soup.find_all(['svg']):

		# Set height and width equal to the viewport if one is not specified
		svg_attrs = tag.attrs
		if "height" not in svg_attrs and "viewBox" in svg_attrs:
			view_box = svg_attrs["viewBox"].split(" ")
			tag["height"] = view_box[3]
		if "width" not in svg_attrs and "viewBox" in svg_attrs:
			view_box = svg_attrs["viewBox"].split(" ")
			tag["width"] = view_box[2]

		# Convert it to a gif (or other specified format)
		fake_url = hashlib.md5(str(tag).encode()).hexdigest()
		convert = config.CONVERT_IMAGES
		convert_to = config.CONVERT_IMAGES_TO_FILETYPE
		fetch_and_cache_image(
			fake_url,
			str(tag).encode('utf-8'),
			resize=config.RESIZE_IMAGES,
			max_width=config.MAX_IMAGE_WIDTH,
			max_height=config.MAX_IMAGE_HEIGHT,
			convert=convert,
			convert_to=convert_to,
			dithering=config.DITHERING_ALGORITHM,
			hash_url=False,
		)
		extension = convert_to.lower() if convert and convert_to else "gif"

		# The _external=True attribute of `url_for` doesn't work here, and will
		# always return `localhost` instead of our host IP / port. So grab that
		# info from the app config directly and prepend it to a relative URL instead.
		relative_url = url_for('serve_cached_image', filename=f"{fake_url}.{extension}")
		url = f"http://{current_app.config['MACPROXY_HOST_AND_PORT']}{relative_url}"
		img_attrs = {"src": url}
		if "height" in svg_attrs:
			img_attrs["height"] = svg_attrs["height"]
		if "width" in svg_attrs:
			img_attrs["width"] = svg_attrs["width"]
		img = soup.new_tag("img", **img_attrs)
		tag.replace_with(img)

	# Use the custom formatter when converting the soup back to a string
	html = soup.decode(formatter=URLAwareHTMLFormatter())

	html = html.replace('<br/>', '<br>')
	html = html.replace('<hr/>', '<hr>')
	
	# Ensure the output is properly encoded
	html_bytes = html.encode('utf-8')

	return html_bytes

if __name__ == "__main__":
	out = transcode_html(
		'<a href="/next">next</a><input type="image" src="/frame.jpg"><meta http-equiv="refresh" content="0;url=/done"><form action="/post"><input name="q"></form>',
		url="http://example.com/start",
		whitelisted_domains=[],
		tags_to_unwrap=[],
		tags_to_strip=[],
		attributes_to_strip=[],
		conversion_table={},
		frontend_base_url="http://proxy.local/web"
	).decode("utf-8")
	assert 'href="http://proxy.local/web?url=http%3A%2F%2Fexample.com%2Fnext"' in out
	assert 'src="http://proxy.local/web?url=http%3A%2F%2Fexample.com%2Fframe.jpg"' in out
	assert 'content="0;url=http://proxy.local/web?url=http%3A%2F%2Fexample.com%2Fdone"' in out
	assert 'action="http://proxy.local/web"' in out
	assert 'name="url"' in out and 'value="http://example.com/post"' in out
