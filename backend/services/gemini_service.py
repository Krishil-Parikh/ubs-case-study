import google.generativeai as genai
from backend.config.settings import settings


class GeminiService:
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.pro = genai.GenerativeModel(settings.gemini_model)
        self.flash = genai.GenerativeModel(settings.gemini_flash_model)

    def generate(self, prompt: str, use_flash: bool = False) -> str:
        model = self.flash if use_flash else self.pro
        response = model.generate_content(prompt)
        return response.text

    async def generate_async(self, prompt: str, use_flash: bool = False) -> str:
        model = self.flash if use_flash else self.pro
        response = await model.generate_content_async(prompt)
        return response.text

    def embed(self, text: str) -> list[float]:
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document",
        )
        return result["embedding"]


gemini_service = GeminiService()
