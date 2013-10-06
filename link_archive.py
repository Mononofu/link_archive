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



class Cache():
  def __init__(self):
    self.s = None
    self.cached = {}

  def fetch(self, url):
    if url not in self.cached:
      content = ""
      if is_raw(url):
        content = b64encode(self.session().get(url).content)
      else:
        content = b64encode(self.session().get(url).text.encode('utf-8'))
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


cache = Cache()


def is_raw(url):
  # Todo - do this check based on the content type of the url
  url = url.split("#")[0].split("?")[0].split(";")[0]
  return url.split(".")[-1].lower() in ["zip", "mp3", "pdf", "anki", "js",
                                        "png", "jpg", "jpeg", "gif", "css",
                                        "xml"] or "css" in url

def crawl(url):
  root = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
  folder = "/".join(url.split("/")[:-1]) + "/"

  if is_raw(url):
    print "saving raw file %s" % url
    page = cache.fetch(url).get()

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
      return filter(lambda l: not cache.has(l).get(), links)

    # assume other raw files (images, js, music) don't contain links
    return []

  print "crawling %s" % url
  page = cache.fetch(url).get()
  soup = BeautifulSoup(page, "lxml")

  # get linked ressources
  images = map(lambda img: img.get('src'), soup.find_all('img'))
  images = filter(lambda img: img is not None, images)
  images = map(lambda img: root + img if img[0] == '/' else img, images)  # make absolute

  scripts = map(lambda s: s.get('src'), soup.find_all('script'))
  scripts = filter(lambda s: s is not None, scripts)
  scripts = map(lambda s: root + s if s[0] == '/' else s, scripts)  # make absolute

  styles = map(lambda s: s.get('href'), soup.find_all('link'))
  styles = filter(lambda s: s is not None, styles)
  styles = map(lambda s: root + s if s[0] == '/' else s, styles)  # make absolute
  styles = filter(isAllowed, styles)

  return filter(lambda l: not cache.has(l).get(), images + scripts + styles)


def mirror(url):
  urls = [url]
  while urls:
    urls += crawl(urls.pop(0))

  with open(os.path.join(cache_dir, 'index.html'), 'w') as f:
    f.write('bla')

  print "trying to cache %s" % cache_dir


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

    # strip of protocol, replace slashes by _ so we can use it as a filename
    cache_name = href.split(':')[1][2:].replace('/', '_')
    if cache_name[-1] == '_':
      cache_name = cache_name[:-1]
    print cache_name

    pelican_dir = os.path.split(instance.settings['PATH'])[0]
    cache_dir = os.path.join(pelican_dir, 'cache', tag, cache_name)

    if not os.path.exists(cache_dir):
      # lazy way to make sure all dirs exist
      try:
        os.makedirs(cache_dir)
      except:
        pass

      # mirror(href, cache_dir)

    archive_link = soup.new_tag('a')
    archive_link.string = "[archived]"
    archive_link['href'] = '/cache/' + tag + '/' + cache_name + '/'
    link.insert_after(archive_link)
    link.insert_after(" ")

  instance._content = soup.decode()


def register():
  signals.content_object_init.connect(content_object_init)