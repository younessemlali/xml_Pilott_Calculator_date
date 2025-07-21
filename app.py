"""
Application Streamlit pour l'édition des dates de contrats HR-XML Pilott
"""

import streamlit as st
from datetime import datetime, date, timedelta
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re
import xml.etree.ElementTree as ET
import uuid
import pytz
from dateutil import parser
import xmlschema

# ============= CONSTANTS =============
XML_ENCODING = 'ISO-8859-1'

NAMESPACES = {
    'hr': 'http://www.hr-xml.org/3',
    'oa': 'http://www.openapplications.org/oagis/9',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIMEZONE = 'Europe/Paris'

INPUT_FILE_PATTERN = r'ASS_\d+_A_ETT\.xml'
OUTPUT_FILE_PATTERN = 'ASS_{timestamp}_AU_ETT.xml'
STAFFING_ACTION_PATTERN = 'ASS_{timestamp}_SA_ETT.xml'

MAX_FLEXIBILITY_DAYS = 10
FLEXIBILITY_DIVISOR = 5

PROCESS_STATUS_UPDATE = 'update'
ASSIGNMENT_STATUS_ACTIVE = 'active'
ACTION_REASON_CODE_FLEXIBILITY = 'PilOTT:FlexibilityUseDate'

ERROR_MESSAGES = {
    'invalid_actual_end': "La date de fin réelle doit être <= à la date de flexibilité maximale",
    'invalid_file_format': "Format de fichier invalide. Attendu: ASS_*_A_ETT.xml",
    'parsing_error': "Erreur lors de l'analyse du fichier XML",
    'validation_error': "Le fichier XML ne respecte pas le schéma XSD",
    'encoding_error': "Erreur d'encodage. Le fichier doit être en ISO-8859-1",
}

# Enregistrer les namespaces
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

# ============= DATE CALCULATIONS =============

def calc_flex_range(start: date, expected_end: date) -> Tuple[date, date, int]:
    """Calcule les dates de flexibilité min et max selon la règle Pilott."""
    duration = (expected_end - start).days + 1
    flex_days = min(MAX_FLEXIBILITY_DAYS, max(1, duration // FLEXIBILITY_DIVISOR))
    flex_min = expected_end - timedelta(days=flex_days)
    flex_max = expected_end + timedelta(days=flex_days)
    return flex_min, flex_max, flex_days

def validate_date_coherence(start_date: date, expected_end_date: date, 
                          actual_end_date: Optional[date] = None) -> Tuple[bool, Optional[str]]:
    """Valide la cohérence globale des dates d'un contrat."""
    if start_date > expected_end_date:
        return False, "La date de début doit être antérieure à la date de fin prévue"
    
    if actual_end_date:
        flex_min, flex_max, _ = calc_flex_range(start_date, expected_end_date)
        if actual_end_date > flex_max:
            return False, ERROR_MESSAGES['invalid_actual_end']
        if actual_end_date < start_date:
            return False, "La date de fin réelle ne peut pas être antérieure au début de mission"
    
    return True, None

def parse_date(date_str: str) -> date:
    """Parse une date au format YYYY-MM-DD."""
    return datetime.strptime(date_str, DATE_FORMAT).date()

def format_date(date_obj: date) -> str:
    """Formate une date au format YYYY-MM-DD."""
    return date_obj.strftime(DATE_FORMAT)

def format_datetime_utc(dt: datetime) -> str:
    """Formate un datetime en UTC au format ISO avec Z."""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    else:
        dt = dt.astimezone(pytz.UTC)
    return dt.strftime(DATETIME_FORMAT)

# ============= XML HANDLING =============

class ContractData:
    """Structure pour stocker les données d'un contrat"""
    def __init__(self):
        self.assignment_id = ""
        self.staffing_supplier_id = ""
        self.start_date = None
        self.expected_end_date = None
        self.actual_end_date = None
        self.flex_min_date = None
        self.flex_max_date = None
        self.original_tree = None
        self.filename = ""

def parse_contract_xml(xml_content: bytes, filename: str = "") -> ContractData:
    """Parse un fichier XML de contrat et extrait les données pertinentes."""
    try:
        root = ET.fromstring(xml_content.decode(XML_ENCODING))
        
        contract = ContractData()
        contract.filename = filename
        contract.original_tree = ET.ElementTree(root)
        
        # Extraire les identifiants
        assignment_elem = root.find('.//hr:Assignment', NAMESPACES)
        if assignment_elem is not None:
            assignment_id_elem = assignment_elem.find('.//hr:AssignmentId', NAMESPACES)
            if assignment_id_elem is not None:
                contract.assignment_id = assignment_id_elem.text or ""
            
            supplier_elem = assignment_elem.find('.//hr:StaffingSupplierId', NAMESPACES)
            if supplier_elem is not None:
                contract.staffing_supplier_id = supplier_elem.text or ""
        
        # Extraire les dates
        date_range_elem = root.find('.//hr:AssignmentDateRange', NAMESPACES)
        if date_range_elem is not None:
            start_elem = date_range_elem.find('hr:StartDate', NAMESPACES)
            if start_elem is not None and start_elem.text:
                contract.start_date = parse_date(start_elem.text)
            
            expected_end_elem = date_range_elem.find('hr:ExpectedEndDate', NAMESPACES)
            if expected_end_elem is not None and expected_end_elem.text:
                contract.expected_end_date = parse_date(expected_end_elem.text)
            
            actual_end_elem = date_range_elem.find('hr:ActualEndDate', NAMESPACES)
            if actual_end_elem is not None and actual_end_elem.text:
                contract.actual_end_date = parse_date(actual_end_elem.text)
            
            flex_min_elem = date_range_elem.find('hr:FlexibilityMinDate', NAMESPACES)
            if flex_min_elem is not None and flex_min_elem.text:
                contract.flex_min_date = parse_date(flex_min_elem.text)
            
            flex_max_elem = date_range_elem.find('hr:FlexibilityMaxDate', NAMESPACES)
            if flex_max_elem is not None and flex_max_elem.text:
                contract.flex_max_date = parse_date(flex_max_elem.text)
        
        # Calculer les dates de flexibilité si nécessaire
        if contract.start_date and contract.expected_end_date:
            if not contract.flex_min_date or not contract.flex_max_date:
                flex_min, flex_max, _ = calc_flex_range(
                    contract.start_date, 
                    contract.expected_end_date
                )
                contract.flex_min_date = flex_min
                contract.flex_max_date = flex_max
        
        return contract
        
    except Exception as e:
        raise ValueError(f"{ERROR_MESSAGES['parsing_error']}: {str(e)}")

def build_au_packet(contract: ContractData) -> ET.ElementTree:
    """Construit un paquet AU (AssignmentUpdate) à partir des données du contrat."""
    root = ET.Element('{' + NAMESPACES['hr'] + '}HRXMLRequest')
    for prefix, uri in NAMESPACES.items():
        root.set(f'xmlns:{prefix}', uri)
    
    # Header
    header = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Header')
    transact_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TransactId')
    transact_elem.text = str(uuid.uuid4())
    timestamp_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TimeStamp')
    timestamp_elem.text = format_datetime_utc(datetime.utcnow())
    
    # Body
    body = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Body')
    assignment = ET.SubElement(body, '{' + NAMESPACES['hr'] + '}Assignment')
    assignment.set('processStatus', PROCESS_STATUS_UPDATE)
    assignment.set('assignmentStatus', ASSIGNMENT_STATUS_ACTIVE)
    
    # AssignmentId
    assignment_id_elem = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}AssignmentId')
    assignment_id_elem.text = contract.assignment_id
    
    # StaffingSupplierId
    supplier_elem = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}StaffingSupplierId')
    supplier_elem.text = contract.staffing_supplier_id
    
    # AssignmentDateRange
    date_range = ET.SubElement(assignment, '{' + NAMESPACES['hr'] + '}AssignmentDateRange')
    
    # Dates
    start_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}StartDate')
    start_elem.text = format_date(contract.start_date)
    
    expected_end_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}ExpectedEndDate')
    expected_end_elem.text = format_date(contract.expected_end_date)
    
    if contract.actual_end_date:
        actual_end_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}ActualEndDate')
        actual_end_elem.text = format_date(contract.actual_end_date)
    
    flex_min_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}FlexibilityMinDate')
    flex_min_elem.text = format_date(contract.flex_min_date)
    
    flex_max_elem = ET.SubElement(date_range, '{' + NAMESPACES['hr'] + '}FlexibilityMaxDate')
    flex_max_elem.text = format_date(contract.flex_max_date)
    
    return ET.ElementTree(root)

def build_staffing_action(contract: ContractData, 
                         flexibility_date: Optional[str] = None,
                         delete: bool = False) -> ET.ElementTree:
    """Construit un StaffingAction pour la date de souplesse."""
    root = ET.Element('{' + NAMESPACES['hr'] + '}HRXMLRequest')
    for prefix, uri in NAMESPACES.items():
        root.set(f'xmlns:{prefix}', uri)
    
    # Header
    header = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Header')
    transact_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TransactId')
    transact_elem.text = str(uuid.uuid4())
    timestamp_elem = ET.SubElement(header, '{' + NAMESPACES['hr'] + '}TimeStamp')
    timestamp_elem.text = format_datetime_utc(datetime.utcnow())
    
    # Body avec StaffingAction
    body = ET.SubElement(root, '{' + NAMESPACES['hr'] + '}Body')
    staffing_action = ET.SubElement(body, '{' + NAMESPACES['hr'] + '}StaffingAction')
    
    assignment_id_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}AssignmentId')
    assignment_id_elem.text = contract.assignment_id
    
    reason_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}ActionReasonCode')
    reason_elem.text = ACTION_REASON_CODE_FLEXIBILITY
    
    comments_elem = ET.SubElement(staffing_action, '{' + NAMESPACES['hr'] + '}ActionTypeComments')
    comments_elem.text = 'delete' if delete else flexibility_date
    
    return ET.ElementTree(root)

def write_xml(tree: ET.ElementTree, output_path: str) -> None:
    """Écrit un ElementTree dans un fichier XML avec encodage ISO-8859-1."""
    _indent(tree.getroot())
    tree.write(output_path, 
               encoding=XML_ENCODING,
               xml_declaration=True,
               method='xml')

def _indent(elem: ET.Element, level: int = 0) -> None:
    """Helper pour indenter le XML"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def generate_output_filename(file_type: str = 'AU') -> str:
    """Génère un nom de fichier de sortie avec timestamp."""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    if file_type == 'SA':
        return STAFFING_ACTION_PATTERN.format(timestamp=timestamp)
    else:
        return OUTPUT_FILE_PATTERN.format(timestamp=timestamp)

# ============= STREAMLIT APP =============

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
        content = uploaded_file.read()
        
        if not validate_filename(uploaded_file.name):
            return {
                'success': False,
                'error': ERROR_MESSAGES['invalid_file_format']
            }
        
        contract = parse_contract_xml(content, uploaded_file.name)
        
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
                        
                        new_start = st.date_input(
                            "Date de début",
                            value=contract.start_date,
                            key=f"start_{idx}",
                            format="YYYY-MM-DD"
                        )
                        
                        new_expected_end = st.date_input(
                            "Date de fin prévue",
                            value=contract.expected_end_date,
                            key=f"expected_{idx}",
                            format="YYYY-MM-DD"
                        )
                        
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
                        
                        if new_start != contract.start_date or new_expected_end != contract.expected_end_date:
                            flex_min, flex_max, flex_days = calc_flex_range(new_start, new_expected_end)
                            
                            contract.start_date = new_start
                            contract.expected_end_date = new_expected_end
                            contract.flex_min_date = flex_min
                            contract.flex_max_date = flex_max
                        
                        st.info(f"**Flexibilité Min:** {format_date(contract.flex_min_date)}")
                        st.info(f"**Flexibilité Max:** {format_date(contract.flex_max_date)}")
                        
                        duration = (contract.expected_end_date - contract.start_date).days + 1
                        flex_days = min(10, max(1, duration // 5))
                        st.metric("Jours de flexibilité", flex_days)
                    
                    with col3:
                        st.subheader("Validations")
                        
                        valid, error_msg = validate_date_coherence(
                            contract.start_date,
                            contract.expected_end_date,
                            new_actual_end
                        )
                        
                        if valid:
                            st.success("✅ Dates cohérentes")
                        else:
                            st.error(f"❌ {error_msg}")
                        
                        contract.actual_end_date = new_actual_end
                        
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
                        if generate_type.startswith("AU"):
                            filename = generate_output_filename('AU')
                            au_tree = build_au_packet(contract)
                            
                            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp:
                                write_xml(au_tree, tmp.name)
                                generated_files.append((filename, tmp.name))
                        
                        else:  # StaffingAction
                            filename = generate_output_filename('SA')
                            sa_tree = build_staffing_action(
                                contract,
                                format_date(flex_date) if not is_delete else None,
                                is_delete
                            )
                            
                            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False) as tmp:
                                write_xml(sa_tree, tmp.name)
                                generated_files.append((filename, tmp.name))
                        
                        add_message(f"✅ {filename} généré", "success")
                        
                    except Exception as e:
                        add_message(f"❌ Erreur génération: {str(e)}", "error")
                
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
