#Python proxy handler

import urllib.request


# Create the object, assign it to a variable
proxy = urllib.request.ProxyHandler({'http': 'westproxy.northgrum.com:80'})

# Construct a new opener using your proxy settings
opener = urllib.request.build_opener(proxy)

# Install the opener at module-level
urllib.request.install_opener(opener)

# Make a request
urllib.request.urlretrieve('http://someurl.com')
