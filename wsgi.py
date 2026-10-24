from dotenv import load_dotenv

load_dotenv(".env.local")  # التشغيل المحلي فقط؛ على Vercel المتغيرات تأتي من إعدادات المشروع
load_dotenv(".env")

from app import create_app  # noqa: E402

app = create_app()
