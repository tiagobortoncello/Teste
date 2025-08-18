# Importar bibliotecas necessárias
import streamlit as st
import re
import pandas as pd
from PyPDF2 import PdfReader
import io

def run_app():
    # --- Custom CSS para estilizar os títulos ---
    st.markdown("""
        <style>
        .title-container {
            text-align: center;
            background-color: #f0f0f0;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .main-title {
            color: #d11a2a;
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 0;
        }
        .subtitle-gil {
            color: gray;
            font-size: 1.5em;
            margin-top: 5px;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- Título e informações ---
    st.markdown("""
        <div class="title-container">
            <h1 class="main-title">Extrator de Documentos do Diário do Legislativo</h1>
            <h4 class="subtitle-gil">GERÊNCIA DE INFORMAÇÃO LEGISLATIVA - GIL/GDI</h4>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()

    st.markdown("<p style='font-size: 1.1em; color: firebrick;'>Por favor, faça o upload do arquivo PDF do **Diário do Legislativo**.</p>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Escolha um arquivo PDF", type="pdf")

    if uploaded_file is not None:
        try:
            reader = PdfReader(uploaded_file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n+", "\n", text)
        except Exception as e:
            st.error(f"Ocorreu um erro ao ler o PDF: {e}")
            return
        
        st.success("PDF lido com sucesso! O processamento começou.")
        
        with st.spinner('Extraindo dados...'):
            # ==========================
            # ABA 1: Normas
            # ==========================
            tipo_map_norma = {
                "LEI": "LEI",
                "RESOLUÇÃO": "RAL",
                "LEI COMPLEMENTAR": "LCP",
                "EMENDA À CONSTITUIÇÃO": "EMC",
                "DELIBERAÇÃO DA MESA": "DLB"
            }
            pattern_norma = re.compile(
                r"^(LEI COMPLEMENTAR|LEI|RESOLUÇÃO|EMENDA À CONSTITUIÇÃO|DELIBERAÇÃO DA MESA) Nº (\d{1,5}(?:\.\d{0,3})?)(?:/(\d{4}))?(?:, DE .+ DE (\d{4}))?$",
                re.MULTILINE
            )
            normas = []
            for match in pattern_norma.finditer(text):
                tipo_extenso = match.group(1)
                numero_raw = match.group(2).replace(".", "")
                ano = match.group(3) if match.group(3) else match.group(4)
                if not ano:
                    continue
                sigla = tipo_map_norma[tipo_extenso]
                normas.append([sigla, numero_raw, ano])
            df_normas = pd.DataFrame(normas)

            # ==========================
            # ABA 2: Proposições
            # ==========================
            tipo_map_prop = {
                "PROJETO DE LEI": "PL",
                "PROJETO DE LEI COMPLEMENTAR": "PLC",
                "INDICAÇÃO": "IND",
                "PROJETO DE RESOLUÇÃO": "PRE",
                "PROPOSTA DE EMENDA À CONSTITUIÇÃO": "PEC",
                "MENSAGEM": "MSG",
                "VETO": "VET"
            }
            pattern_prop = re.compile(
                r"^(PROJETO DE LEI COMPLEMENTAR|PROJETO DE LEI|INDICAÇÃO|PROJETO DE RESOLUÇÃO|PROPOSTA DE EMENDA À CONSTITUIÇÃO|MENSAGEM|VETO) Nº (\d{1,4}\.?\d{0,3}/\d{4})$",
                re.MULTILINE
            )
            
            # Padrão de regex MAIS ROBUSTO para a ementa de utilidade pública
            pattern_utilidade = re.compile(
                r"Declara de utilidade pública\s+a\s+.*?(?:-.*?-)?,\s*com sede no Município de\s+.*?\.",
                re.DOTALL | re.IGNORECASE
            )
            
            proposicoes = []
            prop_matches = list(pattern_prop.finditer(text))
            
            for i, match in enumerate(prop_matches):
                start_idx = match.end()
                # Define o fim do bloco como o início do próximo projeto ou o fim do texto
                end_idx = prop_matches[i+1].start() if i + 1 < len(prop_matches) else len(text)
                block = text[start_idx:end_idx]

                # Ignora proposições com a emenda "Redação do Vencido"
                subseq_text = text[start_idx:start_idx+30]
                if "(Redação do Vencido)" in subseq_text:
                    continue

                tipo_extenso = match.group(1)
                numero_ano = match.group(2).replace(".", "")
                numero, ano = numero_ano.split("/")
                sigla = tipo_map_prop[tipo_extenso]
                
                # Verifica se o bloco de texto é de "Utilidade Pública"
                categoria = ""
                if pattern_utilidade.search(block):
                    categoria = "Utilidade Pública"
                    
                proposicoes.append([sigla, numero, ano, categoria])
            
            df_proposicoes = pd.DataFrame(proposicoes, columns=['Sigla', 'Numero', 'Ano', 'Categoria'])


            # ==========================
            # ABA 3: Requerimentos
            # ==========================
            def classify_req(segment):
                segment_lower = segment.lower()
                if "voto de congratula" in segment_lower:
                    return "Voto de congratulações"
                elif "manifestação de pesar" in segment_lower:
                    return "Manifestação de pesar"
                elif "manifestação de repúdio" in segment_lower:
                    return "Manifestação de repúdio"
                elif "moção de aplauso" in segment_lower:
                    return "Moção de aplauso"
                else:
                    return ""

            requerimentos = []

            # padrões
            rqn_pattern = re.compile(r"^(?:\s*)(Nº)\s+(\d{2}\.?\d{3}/\d{4})\s*,\s*(do|da)", re.MULTILINE)
            rqc_pattern = re.compile(r"^(?:\s*)(nº)\s+(\d{2}\.?\d{3}/\d{4})\s*,\s*(do|da)", re.MULTILINE)
            
            # Padrão mais flexível para o título, ignora o início e fim de linha
            nao_recebidas_header_pattern = re.compile(r"PROPOSIÇÕES\s*NÃO\s*RECEBIDAS", re.IGNORECASE)

            # requerimentos normais (RQN)
            for match in rqn_pattern.finditer(text):
                start_idx = match.start()
                next_match = re.search(r"^(?:\s*)(Nº|nº)\s+(\d{2}\.?\d{3}/\d{4})", text[start_idx + 1:], flags=re.MULTILINE)
                end_idx = (next_match.start() + start_idx + 1) if next_match else len(text)
                block = text[start_idx:end_idx].strip()
                nums_in_block = re.findall(r'\d{2}\.?\d{3}/\d{4}', block)
                if not nums_in_block:
                    continue
                num_part, ano = nums_in_block[0].replace(".", "").split("/")
                classif = classify_req(block)
                requerimentos.append(["RQN", num_part, ano, "", "", classif])

            # requerimentos de congratulações (RQC)
            for match in rqc_pattern.finditer(text):
                start_idx = match
