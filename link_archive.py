"""
Link Archiver
------------------------

This plugin:

- automatically caches all external links locally
- adds a link to the cached copy next to the real link

TODO: Need to add a test.py for this plugin.

"""

import os
import re
from pelican import signals
import logging
import traceback
import commands
import urllib

from bs4 import BeautifulSoup
from PIL import Image
from urlparse import urlparse
import requests

import sqlite3

class Fetcher():
  def __init__(self):
    self.s = None
    self.cached = {}

  def fetch(self, url):
    if url not in self.cached:
      content = ""
      if is_raw(url):
        content = self.session().get(url).content
      else:
        content = self.session().get(url).text.encode('utf-8')
      self.cached[url] = content

    return self.cached[url]

  def has(self, url):
    return url in self.cached

  def session(self):
    if self.s is None:
      self.s = requests.Session()
      self.s.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; http://furida.mu/link-archiver)'})
    return self.s

  def list_pages(self):
    return self.cached.iterkeys()

  def clean_cache(self):
    self.cached = {}


fetcher = Fetcher()


def is_raw(url):
  # Todo - do this check based on the content type of the url
  url = url.split("#")[0].split("?")[0].split(";")[0]
  return url.split(".")[-1].lower() in ["zip", "mp3", "pdf", "anki", "js",
                                        "png", "jpg", "jpeg", "gif", "css",
                                        "xml", "svg", 'ttf', 'woff'] or "css" in url


def crawl(url):
  root = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
  folder = "/".join(url.split("/")[:-1]) + "/"

  def make_absolute(link):
    if link[0] == "/":
      return root + link
    elif "http://" in link or "https://" in link:
      return link
    else:
      full_link = (folder + link).split("/")
      while ".." in full_link:
        i = full_link.index("..")
        full_link.pop(i)
        full_link.pop(i-1)
      return "/".join(full_link)

  if is_raw(url):
    print "saving raw file %s" % url
    page = fetcher.fetch(url)

    # parse css files for linked ressources
    if ".css" in url:
      links = re.findall("url\(([^)]+)\)", page)
      links = map(lambda s: s.strip().replace('"', '').replace("'", ''), links)
      links = map(lambda a: a.split(";")[0], links)
      links = map(make_absolute, links)
      print "searching for", links
      return filter(lambda l: not fetcher.has(l), links)

    # assume other raw files (images, js, music) don't contain links
    return []

  print "crawling %s" % url
  page = fetcher.fetch(url)
  soup = BeautifulSoup(page, "lxml")

  # get linked ressources
  images = map(lambda img: img.get('src'), soup.find_all('img'))
  scripts = map(lambda s: s.get('src'), soup.find_all('script'))
  styles = filter(lambda s: 'stylesheet' in s.get('rel'), soup.find_all('link'))
  styles = map(lambda s: s.get('href'), styles)

  links = filter(lambda l: l is not None, images + scripts + styles)
  links = map(make_absolute, links)  # make absolute
  return filter(lambda l: not fetcher.has(l), links)


def mirror(url, fetcher_dir):
  print "trying to fetcher %s" % cache_dir
  urls = [url]
  while urls:
    url = urls.pop(0)
    try:
      urls += crawl(url)
    except Exception as e:
      print
      logging.exception("error fetching %s" % url)
      traceback.print_exc()
      print

  # finished downloading all content we need, now write it out
  for url in fetcher.list_pages():
    build(url, cache_dir)

  fetcher.clean_cache()


def make_html_link(url, skip_anchor=False):
  url = url.lower()
  path = url.split("#")[0].split("?")[0].split(";")[0]

  if len(path) > 0:
    if path[-1] == "/":
      path += "index.html"
    elif "." not in path.split("/")[-1]:
      path += "/index.html"

  if skip_anchor or "#" not in url:
    return path
  return path + "#" + url.split("#")[-1]

def url2path(url, cache_dir):
  return urllib.unquote(os.path.join(cache_dir,
    make_html_link(url, skip_anchor=True).replace("http://", "").replace(
      "https://", "")))

def build(url, cache_dir):
  path = url2path(url, cache_dir)
  page = fetcher.fetch(url)

  if not os.path.exists(os.path.dirname(path)):
    os.makedirs(os.path.dirname(path))

  if is_raw(url):
    print "dumping %s" % url
    with open(path, "w") as f:
      f.write(page)
    return

  print "building %s as %s" % (url, path)
  soup = BeautifulSoup(page, "lxml")

  def format_link(local_url):
    try:
      # find out how many dirs we need to go up to  be at the base
      # (ie into the dir that contains the current domain)
      slash_count = url.count('/')
      # even if there's no trailing slash the url will get it's own dir
      if url[-1] != '/':
        slash_count += 1
      # subtract two // for the protocoll
      slash_count -= 2

      if local_url[0] == '/':
        # local url - stay on same domain (go up one less)
        return make_html_link(((slash_count - 1) * "../") + local_url[1:])
      elif "http" in local_url:
          base_url = u'{uri.netloc}{uri.path}'.format(uri=urlparse(local_url))
          return make_html_link((slash_count * "../") + base_url)
      else:
        return make_html_link(local_url)
    except:
      return local_url

  for tag in soup.find_all(['img', 'script', 'link']):
    if "href" in tag.attrs:
      tag['href'] = format_link(tag['href'])
    if "src" in tag.attrs:
      tag['src'] = format_link(tag['src'])

  with open(path, "w") as f:
    f.write(soup.prettify(formatter=None).encode('utf-8'))



def content_object_init(instance):

  if instance._content is None:
    return

  content = instance._content
  soup = BeautifulSoup(content)

  tag = instance.url.replace("/", "_")
  if tag[-1] == '_':
    tag = tag[:-1]

  for link in soup('a'):
    href = link['href']

    # don't cache local (=relative) links
    if 'http' not in href:
      continue

    # don't cache links marked as transient
    if "!" == href[0]:
      link['href'] = href[1:]   # strip marker
      continue

    # strip protocol, replace slashes by _ so we can use it as a filename
    cache_name = href.split(':')[1][2:].replace('/', '_')
    if cache_name[-1] == '_':
      cache_name = cache_name[:-1]

    pelican_dir = os.path.split(instance.settings['PATH'])[0]
    cache_dir = os.path.join(pelican_dir, 'cache', tag, cache_name)

    # only mirror if we don't already have the site for that post
    if not os.path.exists(urllib.unquote(cache_dir)):
      mirror(href, cache_dir)

    # add link to archived version after real link
    archive_link = soup.new_tag('a')
    archive_link.string = "cache"
    archive_link['href'] = '/' + url2path(href, os.path.join('cache', tag, cache_name))

    superscript = soup.new_tag('sup')
    superscript.append(archive_link)
    link.insert_after(superscript)

  instance._content = soup.decode()


# copy cached websites to output directory
def copy_cache(instance):
  print "copying cached files"
  pelican_dir = os.path.split(instance.settings['PATH'])[0]

  commands.getoutput("cp -rf %s %s" % (os.path.join(pelican_dir, "cache"),
    os.path.join(pelican_dir, 'output')))

def register():
  signals.content_object_init.connect(content_object_init)
  signals.finalized.connect(copy_cache)
