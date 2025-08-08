import json
import re
from vllm import LLM, SamplingParams
from app.core.qualifier.utils import PROMPT_TEMPLATE_FR
from bs4 import BeautifulSoup

class QualifierService:
    def __init__(self):
        self.llm_args = {
            "model": "TheBloke/deepseek-llm-7b-chat-AWQ",
            "quantization": "awq",
            "gpu_memory_utilization": 0.90,
            "trust_remote_code": True,
            "dtype": "auto"
        }
        self.llm = LLM(**self.llm_args)
        self.tokenizer = self.llm.get_tokenizer()

    def classify(self, url: str, content: str):
        if not content:
            return "contenu_vide", None, {"url": url}

        soup = BeautifulSoup(content, 'html.parser')

        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script_or_style.decompose()

        cleaned_text = soup.get_text(separator='\n', strip=True)
        truncated_content = cleaned_text[:15000]

        sampling_params = SamplingParams(max_tokens=250, temperature=0.1)

        user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=truncated_content)
        
        conversation = [{"role": "user", "content": user_prompt}]
        
        formatted_prompt = self.tokenizer.apply_chat_template(
            conversation, 
            tokenize=False, 
            add_generation_prompt=True
        )

        outputs = self.llm.generate([formatted_prompt], sampling_params)
        raw_text = outputs[0].outputs[0].text.strip()

        try:
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                json_string = match.group(0)
                result = json.loads(json_string)
            else:
                raise ValueError("Aucun bloc JSON trouvé.")
        except (json.JSONDecodeError, ValueError) as e:
            result = {"type_page": "erreur_parsing"}
            
        # On retourne maintenant directement le type de page
        return result.get("type_page", "N/A"), None, None