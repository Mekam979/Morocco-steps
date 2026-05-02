import os
import re

# CONFIGURATION
GITHUB_BASE = "https://cdn.jsdelivr.net/gh/Mekam979/Morocco-steps@main/frontend"
JSDELIVR_URL = f"{GITHUB_BASE}/static/images/"

def upgrade_migration(content):
    # 1. صلح Flask url_for (كاع الحالات)
    # هادي غاتشد حتى اللي فيهم + ville['image_path']
    flask_pattern = r"\{\{\s*url_for\('static',\s*filename=['\"]images/(.*?)['\"]\)\s*\}\}"
    content = re.sub(flask_pattern, rf"'{JSDELIVR_URL}\1'", content)

    # 2. صلح background-image (بلا ما تزيد كوط زايدة)
    bg_pattern = r"url\(['\"]?/?static/images/(.*?)['\"]?\)"
    content = re.sub(bg_pattern, rf"url('{JSDELIVR_URL}\1')", content)

    # 3. صلح onerror (دقة وحدة)
    onerror_pattern = r"this\.src=['\"]+/?static/images/(.*?)['\"]+"
    content = re.sub(onerror_pattern, rf"this.src='{JSDELIVR_URL}\1'", content)

    return content

# ... (نفس الكود ديال os.walk اللي درنا قبل كيعيط لهاد الـ function)
if __name__ == "__main__":
    PROJECT_ROOT = "./frontend" # تأكد من المسار
    for root, dirs, files in os.walk(PROJECT_ROOT):
        for file in files:
            if file.endswith((".html", ".css")): # السكريبت دابا كيقيس حتى الـ CSS
                file_path = os.path.join(root, file)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                new_content = upgrade_migration(content)

                if content != new_content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"✅ Updated: {file_path}")