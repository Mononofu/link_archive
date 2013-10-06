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

      with open(os.path.join(cache_dir, 'index.html'), 'w') as f:
        f.write('bla')

      print "trying to cache %s" % cache_dir

    soup.new_tag(a)
    link.insert_after()

    continue
    # TODO: Pretty sure this isn't the right way to do this, too hard coded.
    # There must be a setting that I should be using?
    src = instance.settings['PATH'] + '/images/' + os.path.split(img['src'])[1]
    im = Image.open(src)
    extra_style = 'width: {}px; height: auto;'.format(im.size[0])

    if instance.settings['RESPONSIVE_IMAGES']:
      extra_style += ' max-width: 100%;'

    if img.get('style'):
      img['style'] += extra_style
    else:
      img['style'] = extra_style

    if img['alt'] == img['src']:
      img['alt'] = ''

    fig = img.find_parent('div', 'figure')
    if fig:
      if fig.get('style'):
        fig['style'] += extra_style
      else:
        fig['style'] = extra_style

  instance._content = soup.decode()


def register():
  signals.content_object_init.connect(content_object_init)