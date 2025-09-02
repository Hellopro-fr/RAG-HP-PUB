import json
import re
from vllm import LLM, SamplingParams
from app.core.qualifier.utils import PROMPT_TEMPLATE_FR
from bs4 import BeautifulSoup

class QualifierService:
    def __init__(self):
        self.llm_args = {
            "model": "Qwen/Qwen3-14B-AWQ",
            "quantization": "awq",
            "gpu_memory_utilization": 0.90,
            "trust_remote_code": True,
            "dtype": "auto",
            "max_model_len": 2048
        }
        self.llm = LLM(**self.llm_args)
        self.tokenizer = self.llm.get_tokenizer()

    def classify(self, url: str, content: str):
        #
        # AUCUN AUTRE CHANGEMENT N'EST NÉCESSAIRE
        #
        if not content:
            return "contenu_vide", None, None
        
        soup = BeautifulSoup(content, 'html.parser')
        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
            tag.decompose()
        cleaned_text = soup.get_text(separator='\\n', strip=True)
        truncated_content = cleaned_text[:15000] # Tronquer les caractères est toujours une bonne sécurité
        
        sampling_params = SamplingParams(max_tokens=250, temperature=0.1)
        user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=truncated_content)
        conversation = [{"role": "user", "content": user_prompt}]
        
        formatted_prompt = self.tokenizer.apply_chat_template(
            conversation, 
            tokenize=False, 
            add_generation_prompt=True,
            enable_thinking=False # Crucial pour obtenir un JSON propre
        )
        
        outputs = self.llm.generate([formatted_prompt], sampling_params)
        raw_text = outputs[0].outputs[0].text.strip()
        
        try:
            # On cherche d'abord un bloc JSON complet
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                json_string = match.group(0)
                result = json.loads(json_string)
            else:
                # Si aucun bloc complet n'est trouvé, on tente de réparer un JSON incomplet
                # C'est utile si le modèle oublie l'accolade fermante
                start_index = raw_text.find('{')
                if start_index != -1:
                    # On prend tout depuis la première accolade et on essaie de fermer
                    repaired_json = raw_text[start_index:] + "}"
                    result = json.loads(repaired_json)
                else:
                    raise ValueError("Aucun début de JSON ('{') trouvé dans la sortie.")

        except (json.JSONDecodeError, ValueError) as e:
            print("--- ERREUR DE PARSING JSON ---")
            print(f"Erreur: {e}")
            print(f"Sortie brute du LLM: '{raw_text}'")
            result = {"type_page": "erreur_parsing"}
            
        return result.get("type_page", "N/A"), None, None