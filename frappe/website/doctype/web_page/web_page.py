# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import frappe, re
import requests, requests.exceptions
from frappe.utils import strip_html
from frappe.website.website_generator import WebsiteGenerator
from frappe.website.router import resolve_route
from frappe.website.doctype.website_slideshow.website_slideshow import get_slideshow
from frappe.website.utils import find_first_image, get_comment_list
from frappe.utils.jinja import render_template
from jinja2.exceptions import TemplateSyntaxError
from frappe.website.utils import get_home_page
from fidetia.cms.utils import load_module_positions, update_positions_size

class WebPage(WebsiteGenerator):
	save_versions = True
	website = frappe._dict(
		template = "templates/generators/web_page.html",
		condition_field = "published",
		page_title_field = "title"
	)

	def get_feed(self):
		return self.title

	def get_context(self, context):
		# if static page, get static content
		if context.slideshow:
			context.update(get_slideshow(self))

		if self.enable_comments:
			context.comment_list = get_comment_list(self.doctype, self.name)

		context.update({
			"style": self.css or "",
			"script": self.javascript or "",
			"header": self.header,
			"title": self.title,
			"text_align": self.text_align,
		})

		context.parents = []

		routeSplit = context.route.split("/")
		count = 0
		while count < len(routeSplit):
			item = frappe.db.get_value("Web Page", routeSplit[count], ["title", "route"], as_dict=1)
			if count != len(routeSplit) - 1:
				if item:
					nuevapagina = frappe._dict(
						name = item.route,
						title = item.title
					)
					context.parents.append(nuevapagina)
			else:
				#Activamos la ruta si estamos en una pagina distinta a la de inicio
				if item.route != get_home_page():
					context.show_breadcrumbs = True
			count = count + 1

		if self.description:
			context.setdefault("metatags", {})["description"] = self.description

		if not self.show_title:
			context["no_header"] = 1

		self.set_metatags(context)
		self.set_breadcrumbs(context)
		self.set_title_and_header(context)

		context.module_positions = load_module_positions(context.web_page_modules)
		try:
			context.left_size = int(context.left_size)
		except:
			context.left_size = 0
		try:
			context.right_size = int(context.right_size)
		except:
			context.right_size = 0
		context.positions_size = update_positions_size(context.module_positions, context.left_size, context.right_size)

		return context

	def render_dynamic(self, context):
		# dynamic
		is_jinja = "<!-- jinja -->" in context.main_section
		if is_jinja or ("{{" in context.main_section):
			try:
				context["main_section"] = render_template(context.main_section,
					context)
				if not "<!-- static -->" in context.main_section:
					context["no_cache"] = 1
			except TemplateSyntaxError:
				if is_jinja:
					raise

	def set_breadcrumbs(self, context):
		"""Build breadcrumbs template (deprecated)"""
		if not "no_breadcrumbs" in context:
			if "<!-- no-breadcrumbs -->" in context.main_section:
				context.no_breadcrumbs = 1

	def set_title_and_header(self, context):
		"""Extract and set title and header from content or context."""
		if not "no_header" in context:
			if "<!-- no-header -->" in context.main_section:
				context.no_header = 1

		if "<!-- title:" in context.main_section:
			context.title = re.findall('<!-- title:([^>]*) -->', context.main_section)[0].strip()

		if context.get("page_titles") and context.page_titles.get(context.pathname):
			context.title = context.page_titles.get(context.pathname)[0]

		# header
		if context.no_header and "header" in context:
			context.header = ""

		if not context.no_header:
			# if header not set and no h1 tag in the body, set header as title
			if not context.header and "<h1" not in context.main_section:
				context.header = context.title

			# add h1 tag to header
			if context.get("header") and not re.findall("<h.>", context.header):
				context.header = "<h1>" + context.header + "</h1>"

		# if title not set, set title from header
		if not context.title and context.header:
			context.title = strip_html(context.header)

	def add_hero(self, context):
		"""Add a hero element if specified in content or hooks.
		Hero elements get full page width."""
		context.hero = ""
		if "<!-- start-hero -->" in context.main_section:
			parts1 = context.main_section.split("<!-- start-hero -->")
			parts2 = parts1[1].split("<!-- end-hero -->")
			context.main_section = parts1[0] + parts2[1]
			context.hero = parts2[0]

	def check_for_redirect(self, context):
		if "<!-- redirect:" in context.main_section:
			frappe.local.flags.redirect_location = \
				context.main_section.split("<!-- redirect:")[1].split("-->")[0].strip()
			raise frappe.Redirect

	def set_metatags(self, context):
		context.metatags = {
			"name": context.title,
			"description": (context.description or "").replace("\n", " ")[:500]
		}

		image = find_first_image(context.main_section or "")
		if image:
			context.metatags["image"] = image

def check_broken_links():
	cnt = 0
	for p in frappe.db.sql("select name, main_section from `tabWeb Page`", as_dict=True):
		for link in re.findall('href=["\']([^"\']*)["\']', p.main_section):
			if link.startswith("http"):
				try:
					res = requests.get(link)
				except requests.exceptions.SSLError:
					res = frappe._dict({"status_code": "SSL Error"})
				except requests.exceptions.ConnectionError:
					res = frappe._dict({"status_code": "Connection Error"})

				if res.status_code!=200:
					print "[{0}] {1}: {2}".format(res.status_code, p.name, link)
					cnt += 1
			else:
				link = link[1:] # remove leading /
				link = link.split("#")[0]

				if not resolve_route(link):
					print p.name + ":" + link
					cnt += 1

	print "{0} links broken".format(cnt)
