"""
Application Streamlit pour l'édition des dates de contrats HR-XML Pilott
"""

import streamlit as st
from datetime import datetime, date
import tempfile
from pathlib import Path
from typing import List, Dict
import re

from pilott_editor.constants import (
    INPUT_FILE_PATTERN,
    ERROR_MESSAGES,
    XML_ENCODING
)
from pilott_editor.date_calc import (
    calc_flex_range,
    validate_date_coherence,
    format_date,
    parse_date,
    utc_to_paris
)
from pilott_editor.xml_utils import (
    parse_contract_xml,
    update_contract_dates,
    build_au_packet,
    build_staffing_action,
    write_xml,
    validate_xml_schema,
    generate_output_filename,
    ContractData
)


# Configuration de la page
st.set_page_config(
    page_title="Pilott Date Editor",
    page_icon="📅",
    layout="wide"
)

# État de session
if 'contracts' not in st.session_state:
    st.session_state.contracts = []
if 'messages' not in st.session_state:
    st.session_state.messages = []


def add_message(message: str, msg_type: str = "info"):
    """Ajoute un message au log"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.messages.append({
        'time': timestamp,
        'type': msg_type,
        'message': message
    })


def validate_filename(filename: str) -> bool:
    """Valide le format du nom de fichier"""
    return bool(re.match(INPUT_FILE_PATTERN, filename))


def process_uploaded_file(uploaded_file) -> Dict:
    """Traite un fichier uploadé"""
    try:
        # Lire le contenu
        content = uploaded_file.read()
        
        # Valider le nom de fichier
        if not validate_filename(uploaded_file.name):
            return {
                'success': False,
                'error': ERROR_MESSAGES['invalid_file_format']
            }
        
        # Parser le XML
        contract = parse_contract_xml(content, uploaded_file.name)
        
        # Valider les dates
        if contract.start_date and contract.expected_end_date:
            valid, error_msg = validate_date_coherence(
                contract.start_date,
                contract.expected_end_date,
                contract.actual_end_date
            )
            
            if not valid:
                return {
                    'success': False,
                    'error': error_msg
                }
        
        return {
            'success': True,
            'contract': contract
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def main():
    # Header
    st.title("🔧 Pilott Date Editor")
    st.markdown("**Éditeur de dates pour contrats HR-XML conformes aux règles Pilott**")
    
    # Sidebar pour les actions
    with st.sidebar:
        st.header("📁 Chargement des fichiers")
        
        uploaded_files = st.file_uploader(
            "Glissez vos fichiers XML ici",
            type=['xml'],
            accept_multiple_files=True,
            help="Format attendu: ASS_*_A_ETT.xml"
        )
        
        if uploaded_files:
            if st.button("🔄 Charger les fichiers", type="primary"):
                st.session_state.contracts = []
                
                for file in uploaded_files:
                    result = process_uploaded_file(file)
                    
                    if result['success']:
                        st.session_state.contracts.append(result['contract'])
                        add_message(f"✅ {file.name} chargé avec succès", "success")
                    else:
                        add_message(f"❌ {file.name}: {result['error']}", "error")
        
        st.markdown("---")
        
        if st.button("🗑️ Réinitialiser"):
            st.session_state.contracts = []
            st.session_state.messages = []
            st.rerun()
    
    # Zone principale
    if st.session_state.contracts:
        tab1, tab2, tab3 = st.tabs(["📊 Édition des dates", "📄 Génération AU", "📋 Log"])
        
        with tab1:
            st.header("Contrats chargés")
            
            for idx, contract in enumerate(st.session_state.contracts):
                with st.expander(f"📄 {contract.filename} - ID: {contract.assignment_id}", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.subheader("Dates principales")
                        
                        # Date de début
                        new_start = st.date_input(
                            "Date de début",
                            value=contract.start_date,
                            key=f"start_{idx}",
                            format="YYYY-MM-DD"
                        )
                        
                        # Date de fin prévue
                        new_expected_end = st.date_input(
                            "Date de fin prévue",
                            value=contract.expected_end_date,
                            key=f"expected_{idx}",
                            format="YYYY-MM-DD"
                        )
                        
                        # Date de fin réelle (optionnelle)
                        has_actual_end = st.checkbox(
                            "Date de fin réelle définie",
                            value=contract.actual_end_date is not None,
                            key=f"has_actual_{idx}"
                        )
                        
                        if has_actual_end:
                            new_actual_end = st.date_input(
                                "Date de fin réelle",
                                value=contract.actual_end_date or new_expected_end,
                                key=f"actual_{idx}",
                                format="YYYY-MM-DD"
                            )
                        else:
                            new_actual_end = None
                    
                    with col2:
                        st.subheader("Dates de flexibilité")
                        
                        # Recalculer si les dates principales ont changé
                        if new_start != contract.start_date or new_expected_end != contract.expected_end_date:
                            flex_min, flex_max, flex_days = calc_flex_range(new_start, new_expected_end)
                            
                            # Mettre à jour le contrat
                            contract.start_date = new_start
                            contract.expected_end_date = new_expected_end
                            contract.flex_min_date = flex_min
                            contract.flex_max_date = flex_max
                        
                        # Affichage des dates de flexibilité
                        st.info(f"**Flexibilité Min:** {format_date(contract.flex_min_date)}")
                        st.info(f"**Flexibilité Max:** {format_date(contract.flex_max_date)}")
                        
                        # Calcul et affichage du nombre de jours
                        duration = (contract.expected_end_date - contract.start_date).days + 1
                        flex_days = min(10, max(1, duration // 5))
                        st.metric("Jours de flexibilité", flex_days)
                    
                    with col3:
                        st.subheader("Validations")
                        
                        # Valider la cohérence
                        valid, error_msg = validate_date_coherence(
                            contract.start_date,
                            contract.expected_end_date,
                            new_actual_end
                        )
                        
                        if valid:
                            st.success("✅ Dates cohérentes")
                        else:
                            st.error(f"❌ {error_msg}")
                        
                        # Mettre à jour la date de fin réelle
                        contract.actual_end_date = new_actual_end
                        
                        # Info sur la durée
                        st.metric(
                            "Durée totale (jours)",
                            (contract.expected_end_date - contract.start_date).days + 1
                        )
        
        with tab2:
            st.header("Génération des fichiers AU")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                contracts_to_generate = st.multiselect(
                    "Sélectionnez les contrats à générer",
                    options=[f"{c.filename} - {c.assignment_id}" for c in st.session_state.contracts],
                    default=[f"{c.filename} - {c.assignment_id}" for c in st.session_state.contracts]
                )
            
            with col2:
                generate_type = st.radio(
                    "Type de génération",
                    ["AU (Mise à jour)", "SA (Date souplesse)"]
                )
            
            if generate_type == "SA (Date souplesse)":
                col3, col4 = st.columns(2)
                with col3:
                    flex_date = st.date_input(
                        "Date d'utilisation de la souplesse",
                        value=date.today(),
                        format="YYYY-MM-DD"
                    )
                with col4:
                    is_delete = st.checkbox("Supprimer la souplesse")
            
            if st.button("🚀 Générer les fichiers", type="primary"):
                generated_files = []
                
                for idx, contract_str in enumerate(contracts_to_generate):
                    contract = st.session_state.contracts[idx]
                    
                    try:
                        # Générer le nom de fichier
                        if generate_type.startswith("AU"):
                            filename = generate_output_filename('AU')
                            
                            # Mettre à jour les dates dans l'arbre XML
                            update_contract_dates(contract)
                            
                            # Construire le paquet AU
                            au_tree = build_au_packet(contract)
                            
                            # Écrire dans un fichier temporaire
                            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp:
                                write_xml(au_tree, tmp.name)
                                generated_files.append((filename, tmp.name))
                        
                        else:  # StaffingAction
                            filename = generate_output_filename('SA')
                            
                            # Construire le StaffingAction
                            sa_tree = build_staffing_action(
                                contract,
                                format_date(flex_date) if not is_delete else None,
                                is_delete
                            )
                            
                            # Écrire dans un fichier temporaire
                            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp:
                                write_xml(sa_tree, tmp.name)
                                generated_files.append((filename, tmp.name))
                        
                        add_message(f"✅ {filename} généré", "success")
                        
                    except Exception as e:
                        add_message(f"❌ Erreur génération: {str(e)}", "error")
                
                # Afficher les fichiers générés pour téléchargement
                if generated_files:
                    st.success(f"✅ {len(generated_files)} fichier(s) généré(s)")
                    
                    for filename, filepath in generated_files:
                        with open(filepath, 'rb') as f:
                            content = f.read()
                        
                        st.download_button(
                            label=f"📥 Télécharger {filename}",
                            data=content,
                            file_name=filename,
                            mime="application/xml"
                        )
                        
                        # Nettoyer le fichier temporaire
                        Path(filepath).unlink()
        
        with tab3:
            st.header("Journal des opérations")
            
            if st.session_state.messages:
                for msg in reversed(st.session_state.messages):
                    if msg['type'] == 'error':
                        st.error(f"**{msg['time']}** - {msg['message']}")
                    elif msg['type'] == 'success':
                        st.success(f"**{msg['time']}** - {msg['message']}")
                    else:
                        st.info(f"**{msg['time']}** - {msg['message']}")
            else:
                st.info("Aucune opération enregistrée")
    
    else:
        # Page d'accueil
        st.info("👈 Utilisez la barre latérale pour charger vos fichiers XML")
        
        with st.expander("📖 Guide rapide"):
            st.markdown("""
            ### Comment utiliser l'application
            
            1. **Chargez vos fichiers** dans la barre latérale (format: ASS_*_A_ETT.xml)
            2. **Éditez les dates** dans l'onglet "Édition des dates"
            3. **Générez les fichiers AU** dans l'onglet "Génération AU"
            4. **Téléchargez** les fichiers générés
            
            ### Règles de calcul
            
            - **Flexibilité** = ⌊(durée calendaire / 5)⌋ jours, plafonné à 10
            - **Date fin réelle** doit être ≤ FlexibilityMaxDate
            - Les dates sont automatiquement recalculées
            """)


if __name__ == "__main__":
    main()
