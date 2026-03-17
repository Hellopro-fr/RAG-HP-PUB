from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import trafilatura

app = Flask(__name__)

@app.route('/clean', methods=['POST'])
def clean_html():
    data = request.get_json(force=True)
    html_content = data.get("html_content", "")
    texte_trafilatura = trafilatura.extract(html_content, include_comments=False, include_tables=False)
    soup = BeautifulSoup(html_content, "html.parser")
    texte_bs4 = soup.get_text(separator="\n", strip=True)
    texte_propre = texte_trafilatura if texte_trafilatura else texte_bs4

    return jsonify({"clean_text": texte_propre})

@app.route('/', methods=['GET'])
def home():
    return "API Flask est en ligne"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
