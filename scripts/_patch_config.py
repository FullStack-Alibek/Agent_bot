"""Config faylini xavfsiz tahrirlash yordamchisi (bir martalik skript)."""
import io
import sys

path = r"D:\Agent\bot\bot\config.py"
with io.open(path, "r", encoding="utf-8") as fh:
    text = fh.read()

anchor = "    database_url: str = \"sqlite+aiosqlite:///./data/distribution.db\"\n    db_echo: bool = False\n"

addition = anchor + """
    # ---------------- Backend (Laravel) integratsiyasi ----------------
    #: Backend API bazaviy manzili (masalan `http://127.0.0.1:8000/api`).
    #: Bo'sh bo'lsa bot faqat lokal bazadan foydalanadi (offline rejim).
    backend_url: str = ""
    #: Bot <-> backend ichki (internal) API tokeni (`BOT_API_TOKEN`).
    backend_token: SecretStr = SecretStr("")
    #: HTTP so'rov timeout (sekund).
    backend_timeout: float = 10.0
    #: Backend integratsiyasini yoqish (backend_url va token bo'lishi shart).
    backend_enabled: bool = True
"""

if "backend_url" in text:
    print("allaqachon qo'shilgan")
    sys.exit(0)

if anchor not in text:
    print("ANCHOR TOPILMADI")
    sys.exit(1)

text = text.replace(anchor, addition, 1)

# Property qo'shish
prop_anchor = "    @property\n    def token(self) -> str:\n        return self.bot_token.get_secret_value()\n"
prop_addition = prop_anchor + """
    @property
    def backend_api_url(self) -> str:
        \"\"\"Backend API manzili (oxiridagi `/` olib tashlanadi).\"\"\"
        return self.backend_url.rstrip("/")

    @property
    def backend_active(self) -> bool:
        \"\"\"Backend integratsiyasi yoqilganmi (URL va token bor).\"\"\"
        return bool(
            self.backend_enabled
            and self.backend_url.strip()
            and self.backend_token.get_secret_value().strip()
        )

    @property
    def backend_api_token(self) -> str:
        return self.backend_token.get_secret_value()
"""
text = text.replace(prop_anchor, prop_addition, 1)

with io.open(path, "w", encoding="utf-8") as fh:
    fh.write(text)

print("OK")
