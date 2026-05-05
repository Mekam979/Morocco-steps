import os

BASE_URL = "https://cdn.jsdelivr.net/gh/Mekam979/Morocco-steps@main"

for root, dirs, files in os.walk("frontend"):
    for file in files:
        if file.endswith(".html"):
            path = os.path.join(root, file)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            content = content.replace(
                'src="/static/',
                f'src="{BASE_URL}/frontend/static/'
            )

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

print("Done ✅")