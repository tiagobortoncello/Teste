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
            
            # Padrão de regex para a ementa de utilidade pública
            pattern_utilidade = re.compile(
                r"Declara de utilidade pública a (.*?)-.*?-, com sede no Município de (.*?)\.",
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
                utilidade_publica = ""
                if pattern_utilidade.search(block):
                    utilidade_publica = "Utilidade Pública"
                    
                proposicoes.append([sigla, numero, ano, utilidade_publica])
            
            df_proposicoes = pd.DataFrame(proposicoes, columns=['Sigla', 'Numero', 'Ano', 'Utilidade Pública'])


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
                start_idx = match.start()
                next_match = re.search(r"^(?:\s*)(Nº|nº)\s+(\d{2}\.?\d{3}/\d{4})", text[start_idx + 1:], flags=re.MULTILINE)
                end_idx = (next_match.start() + start_idx + 1) if next_match else len(text)
                block = text[start_idx:end_idx].strip()
                nums_in_block = re.findall(r'\d{2}\.?\d{3}/\d{4}', block)
                if not nums_in_block:
                    continue
                num_part, ano = nums_in_block[0].replace(".", "").split("/")
                classif = classify_req(block)
                requerimentos.append(["RQC", num_part, ano, "", "", classif])
            
            # requerimentos NÃO recebidos
            header_match = nao_recebidas_header_pattern.search(text)
            if header_match:
                start_idx = header_match.end()
                # Define o final do bloco de texto como o próximo cabeçalho ou o final do arquivo
                next_section_pattern = re.compile(r"^\s*(\*?)\s*.*\s*(\*?)\s*$", re.MULTILINE)
                next_section_match = next_section_pattern.search(text, start_idx)
                end_idx = next_section_match.start() if next_section_match else len(text)
                
                nao_recebidos_block = text[start_idx:end_idx]
                
                # Padrão para extrair os números dos requerimentos dentro do bloco
                rqn_nao_recebido_pattern = re.compile(r"REQUERIMENTO Nº (\d{2}\.?\d{3}/\d{4})", re.IGNORECASE)
                
                for match in rqn_nao_recebido_pattern.finditer(nao_recebidos_block):
                    numero_ano = match.group(1).replace(".", "")
                    num_part, ano = numero_ano.split("/")
                    requerimentos.append(["RQN", num_part, ano, "", "", "NÃO RECEBIDO"])


            # remover duplicados
            unique_reqs = []
            seen = set()
            for r in requerimentos:
                key = (r[0], r[1], r[2])
                if key not in seen:
                    seen.add(key)
                    unique_reqs.append(r)
            df_requerimentos = pd.DataFrame(unique_reqs)

            # ==========================
            # ABA 4: Pareceres
            # ==========================
            found_projects = {}
            emenda_pattern = re.compile(r"^(?:\s*)EMENDA Nº (\d+)\s*", re.MULTILINE)
            substitutivo_pattern = re.compile(r"^(?:\s*)SUBSTITUTIVO Nº (\d+)\s*", re.MULTILINE)
            project_pattern = re.compile(
                r"Conclusão\s*([\s\S]*?)(Projeto de Lei|PL|Projeto de Resolução|PRE|Proposta de Emenda à Constituição|PEC|Projeto de Lei Complementar|PLC|Requerimento)\s+(?:nº|Nº)?\s*(\d{1,}\.??\d{3})\s*/\s*(\d{4})",
                re.IGNORECASE | re.DOTALL
            )
            all_matches = list(emenda_pattern.finditer(text)) + list(substitutivo_pattern.finditer(text))
            all_matches.sort(key=lambda x: x.start())
            
            for title_match in all_matches:
                text_before_title = text[:title_match.start()]
                last_project_match = None
                for match in project_pattern.finditer(text_before_title):
                    last_project_match = match
                if last_project_match:
                    sigla_raw = last_project_match.group(2)
                    sigla_map = {
                        "requerimento": "RQN",
                        "projeto de lei": "PL",
                        "pl": "PL",
                        "projeto de resolução": "PRE",
                        "pre": "PRE",
                        "proposta de emenda à constituição": "PEC",
                        "pec": "PEC",
                        "projeto de lei complementar": "PLC",
                        "plc": "PLC"
                    }
                    sigla = sigla_map.get(sigla_raw.lower(), sigla_raw.upper())
                    numero = last_project_match.group(3).replace(".", "")
                    ano = last_project_match.group(4)
                    project_key = (sigla, numero, ano)
                    item_type = "EMENDA" if "EMENDA" in title_match.group(0).upper() else "SUBSTITUTIVO"
                    if project_key not in found_projects:
                        found_projects[project_key] = set()
                    found_projects[project_key].add(item_type)
            
            pareceres = []
            for (sigla, numero, ano), types in found_projects.items():
                type_str = "SUB/EMENDA" if len(types) > 1 else list(types)[0]
                pareceres.append([sigla, numero, ano, type_str])
            df_pareceres = pd.DataFrame(pareceres)
            
            st.success("Dados extraídos com sucesso! ✅")
            st.divider()

            # ==========================
            # SALVAR EM EXCEL
            # ==========================
            output = io.BytesIO()
            excel_file_name = "resultado_extraido.xlsx"
            
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_normas.to_excel(writer, sheet_name="Normas", index=False, header=False)
                df_proposicoes.to_excel(writer, sheet_name="Proposicoes", index=False, header=True)
                df_requerimentos.to_excel(writer, sheet_name="Requerimentos", index=False, header=False)
                df_pareceres.to_excel(writer, sheet_name="Pareceres", index=False, header=False)
            
            output.seek(0)

            st.download_button(
                label="Clique aqui para baixar o arquivo Excel",
                data=output,
                file_name=excel_file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.info("O download do arquivo Excel com todos os dados extraídos está pronto.")

# Executar
if __name__ == "__main__":
    run_app()
