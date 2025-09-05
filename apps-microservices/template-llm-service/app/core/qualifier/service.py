import json
import re
from vllm import LLM, SamplingParams
from .utils import PROMPT_TEMPLATE_FR
from bs4 import BeautifulSoup

class QualifierService:
    def __init__(self):
        self.llm_args = {
            "model": "Qwen/Qwen3-14B-AWQ",
            "quantization": "awq",
            # --- LEVIER 1 : UTILISATION DE LA MÉMOIRE POUR UN L4 ---
            # On peut être un peu plus agressif avec 24 Go de VRAM
            "gpu_memory_utilization": 0.85,
            "trust_remote_code": True,
            "dtype": "auto",
            # --- LEVIER 2 : LONGUEUR MAXIMALE ADAPTÉE AU L4 ---
            # 8192 est une valeur ambitieuse mais qui devrait passer sur un L4.
            # Si vous rencontrez encore des erreurs de mémoire, réduisez à 6144 ou 4096.
            "max_model_len": 8192
        }
        self.llm = LLM(**self.llm_args)
        self.tokenizer = self.llm.get_tokenizer()

    def classify(self, url: str, content: str):
        if not content:
            return "contenu_vide", None, None
        
        soup = BeautifulSoup(content, 'html.parser')
        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
            tag.decompose()
        cleaned_text = soup.get_text(separator='\n', strip=True)
        
        # --- LEVIER 3 : TRONCATURE PAR TOKENS ADAPTÉE ---
        # On garde une marge de sécurité (ex: 1024 tokens pour le prompt et la réponse)
        max_content_tokens = self.llm_args["max_model_len"] - 1024 # 8192 - 1024 = 7168

        content_tokens = self.tokenizer.encode(cleaned_text)

        if len(content_tokens) > max_content_tokens:
            truncated_tokens = content_tokens[:max_content_tokens]
            truncated_content = self.tokenizer.decode(truncated_tokens)
        else:
            truncated_content = cleaned_text
        
        # ... (le reste de la fonction est identique et correct) ...
        sampling_params = SamplingParams(max_tokens=250, temperature=0.1)
        user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=truncated_content)
        conversation = [{"role": "user", "content": user_prompt}]
        
        formatted_prompt = self.tokenizer.apply_chat_template(
            conversation, 
            tokenize=False, 
            add_generation_prompt=True,
            enable_thinking=False
        )
        
        final_prompt_tokens = self.tokenizer.encode(formatted_prompt)
        if len(final_prompt_tokens) >= self.llm_args["max_model_len"]:
             print(f"--- ERREUR CRITIQUE : Le prompt final ({len(final_prompt_tokens)} tokens) dépasse la limite de {self.llm_args['max_model_len']}. ---")
             return "erreur_prompt_trop_long", None, None

        outputs = self.llm.generate([formatted_prompt], sampling_params)
        raw_text = outputs[0].outputs[0].text.strip()
        
        try:
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                json_string = match.group(0)
                result = json.loads(json_string)
            else:
                start_index = raw_text.find('{')
                if start_index != -1:
                    repaired_json = raw_text[start_index:] + "}"
                    result = json.loads(repaired_json)
                else:
                    raise ValueError("Aucun début de JSON ('{') trouvé dans la sortie.")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"--- ERREUR DE PARSING JSON --- \nErreur: {e} \nSortie brute: '{raw_text}'")
            result = {"type_page": "erreur_parsing"}
            
        return result.get("type_page", "N/A"), None, None