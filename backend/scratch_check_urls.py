import requests
import json

urls = [
    "https://res.cloudinary.com/darytb39v/image/upload/f_auto,q_auto/villes/kenitra.png",
    "https://res.cloudinary.com/darytb39v/image/upload/f_auto,q_auto/villes/marrakech.jpg",
    "https://res.cloudinary.com/darytb39v/image/upload/f_auto,q_auto/attractions/LaguneDakhla.jpg"
]

results = {}
for url in urls:
    try:
        resp = requests.head(url, timeout=5)
        results[url] = resp.status_code
    except Exception as e:
        results[url] = str(e)

print(json.dumps(results, indent=2))
