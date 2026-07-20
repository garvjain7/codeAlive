import urllib.request
urls = [
    'https://cdn.jsdelivr.net/npm/@codemirror/view@6.36.0/dist/index.js',
    'https://unpkg.com/@codemirror/view@6.36.0/dist/index.js',
    'https://cdn.jsdelivr.net/npm/@codemirror/view@6.36.0/+esm',
    'https://unpkg.com/@codemirror/view@6.36.0/package.json',
]
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(200).decode('utf-8','ignore')
            print(url, '->', r.status, body[:120].replace('\n',' '))
    except Exception as e:
        print(url, 'ERR', e)
