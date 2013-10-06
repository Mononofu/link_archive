"""
Link Archiver
------------------------

This plugin:

- automatically caches all external links locally
- adds a link to the cached copy next to the real link

TODO: Need to add a test.py for this plugin.

"""

import os

from pelican import signals

from bs4 import BeautifulSoup
from PIL import Image
from urlparse import urlparse
import requests


class Cache():
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


cache = Cache()


def is_raw(url):
  # Todo - do this check based on the content type of the url
  url = url.split("#")[0].split("?")[0].split(";")[0]
  return url.split(".")[-1].lower() in ["zip", "mp3", "pdf", "anki", "js",
                                        "png", "jpg", "jpeg", "gif", "css",
                                        "xml", "svg", 'ttf', 'woff'] or "css" in url

def crawl(url):
  root = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
  folder = "/".join(url.split("/")[:-1]) + "/"

  if is_raw(url):
    print "saving raw file %s" % url
    page = cache.fetch(url)

    # parse css files for linked ressources
    if ".css" in url:
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

      links = re.findall("url\(([^)]+)\)", page)
      links = map(lambda s: s.strip().replace('"', '').replace("'", ''), links)
      links = map(lambda a: a.split(";")[0], links)
      links = map(make_absolute, links)
      print "searching for", links
      return filter(lambda l: not cache.has(l), links)

    # assume other raw files (images, js, music) don't contain links
    return []

  print "crawling %s" % url
  page = cache.fetch(url)
  soup = BeautifulSoup(page, "lxml")

  # get linked ressources
  images = map(lambda img: img.get('src'), soup.find_all('img'))
  images = filter(lambda img: img is not None, images)
  images = map(lambda img: root + img if img[0] == '/' else img, images)  # make absolute

  scripts = map(lambda s: s.get('src'), soup.find_all('script'))
  scripts = filter(lambda s: s is not None, scripts)
  scripts = map(lambda s: root + s if s[0] == '/' else s, scripts)  # make absolute

  styles = filter(lambda s: 'stylesheet' in s.get('rel'), soup.find_all('link'))
  styles = map(lambda s: s.get('href'), styles)
  styles = filter(lambda s: s is not None, styles)
  styles = map(lambda s: root + s if s[0] == '/' else s, styles)  # make absolute

  return filter(lambda l: not cache.has(l), images + scripts + styles)


def mirror(url, cache_dir):
  print "trying to cache %s" % cache_dir
  urls = [url]
  while urls:
    try:
      urls += crawl(urls.pop(0))
    except:
      pass

  # finished downloading all content we need, now write it out
  for url in cache.list_pages():
    build(url, cache_dir)

  cache.clean_cache()


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
  return os.path.join(cache_dir,
    make_html_link(url, skip_anchor=True).replace("http://", "").replace("https://", ""))

def build(url, cache_dir):
  path = url2path(url, cache_dir)
  page = cache.fetch(url)

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
      if local_url[0] == '/':
        return make_html_link(((url.count("/") - 2) * "../") + local_url[1:])
      elif "http" in local_url:
          base_url = u'{uri.netloc}{uri.path}'.format(uri=urlparse(local_url))
          return make_html_link(((url.count("/") - 1) * "../") + base_url)
      else:
        return make_html_link(local_url)
    except:
      return local_url

  for tag in soup.find_all(['a', 'img', 'script', 'link']):
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

  print tag

  for link in soup('a'):
    href = link['href']

    # don't cache local (=relative) links
    if 'http' not in href:
      continue

    # strip protocol, replace slashes by _ so we can use it as a filename
    cache_name = href.split(':')[1][2:].replace('/', '_')
    if cache_name[-1] == '_':
      cache_name = cache_name[:-1]
    print cache_name

    pelican_dir = os.path.split(instance.settings['PATH'])[0]
    cache_dir = os.path.join(pelican_dir, 'cache', tag, cache_name)

    # only mirror if we don't already have the site for that post
    if not os.path.exists(cache_dir):
      mirror(href, cache_dir)

    # add link to archived version after real link
    archive_link = soup.new_tag('a')
    archive_link.string = "[archived]"
    archive_link['href'] = url2path(href, os.path.join('cache', tag, cache_name))
    print 
    print
    print archive_link['href']
    print 
    print
    link.insert_after(archive_link)
    link.insert_after(" ")

  instance._content = soup.decode()


def register():
  signals.content_object_init.connect(content_object_init)