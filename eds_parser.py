import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import logging
import re
import struct

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EdsParser:
    def __init__(self, file_path):
        """
        Initialize the EDS parser with the path to the .eds file.
        """
        self.file_path = file_path

    def parse(self):
        """
        Main method to parse the EDS file.
        Returns a dictionary containing metadata, samples, and melt curve data.
        """
        results = {
            "metadata": {},
            "samples": {}, # mapped by sample_id for internal use, or list for DB
            "wells": {},   # mapped by position
            "melt_curves": []
        }

        try:
            with zipfile.ZipFile(self.file_path, 'r') as z:
                # 1. Metadata & Plate Setup
                # The main XML is usually at apldbio/sds/experiment.xml
                experiment_xml_path = "apldbio/sds/experiment.xml"
                
                if experiment_xml_path in z.namelist():
                    with z.open(experiment_xml_path) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        # Strip namespaces to make searching easier
                        self._strip_namespaces(root)
                        
                        # Extract Metadata
                        results["metadata"] = self._extract_metadata(root)
                        
                        # Extract Samples
                        results["samples"] = self._extract_samples(root)
                        
                        # Extract Wells (Plate Setup)
                        results["wells"] = self._extract_wells(root, results["samples"])
                else:
                    logger.error(f"Could not find {experiment_xml_path} in archive.")
                    return None

                # 2. Raw Data Extraction
                # Attempt to read binary files in apldbio/sds/quant/
                # Fallback to XML if binary parsing is too opaque
                results["melt_curves"] = self._extract_melt_curves(z, results["wells"])

        except zipfile.BadZipFile:
            logger.error(f"Error: {self.file_path} is not a valid zip file.")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return None

        return results

    def _strip_namespaces(self, element):
        """Recursively strip namespaces from XML tags."""
        for elem in element.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

    def _extract_metadata(self, root):
        """Extracts run metadata."""
        metadata = {}
        metadata['run_name'] = root.findtext('.//Name')
        metadata['instrument_serial'] = root.findtext('.//InstrumentSerialNumber')
        metadata['run_start_time'] = root.findtext('.//RunStarted')
        
        # Fallbacks/Clean up
        if not metadata['run_name']:
             metadata['run_name'] = "Unknown Run"
             
        return metadata

    def _extract_samples(self, root):
        """
        Extracts sample definitions.
        Returns a dict: {sample_id: {'name': sample_name, 'description': ...}}
        """
        samples = {}
        # Locate the <Samples> collection
        # Structure varies, but usually <Plate><Samples><Sample>...
        for sample in root.findall('.//Sample'):
            # Try to get ID from attribute or child
            s_id = sample.get('ID')
            s_name = sample.findtext('Name')
            s_desc = sample.findtext('Description')
            
            if s_id and s_name:
                samples[s_id] = {
                    'name': s_name, 
                    'description': s_desc
                }
        return samples

    def _extract_wells(self, root, sample_map):
        """
        Extracts well definitions and links them to samples.
        Returns dict: { 'A01': { 'sample_name': ..., 'tm': ... } }
        """
        wells = {}
        for well in root.findall('.//Well'):
            # Coordinates
            try:
                row = int(well.findtext('Row', '-1'))
                col = int(well.findtext('Col', '-1'))
            except ValueError:
                continue

            if row < 0 or col < 0:
                continue

            # Convert to A01 format
            row_char = chr(65 + row)
            well_pos = f"{row_char}{col+1:02d}"

            # Find Sample info
            # Usually <SampleRef ID="..."/> or inside a <Target>
            sample_name = None
            sample_ref = well.find('.//SampleRef')
            if sample_ref is not None:
                s_id = sample_ref.get('ID')
                if s_id in sample_map:
                    sample_name = sample_map[s_id]['name']
            
            # Simple check for direct name if ref failed
            if not sample_name:
                sample_name = well.findtext('SampleName')

            # Extract Melting Temp (Tm) if available (often pre-calculated in XML)
            # This location is highly variable; checking common tags
            tm_value = None
            # e.g., <Result><Tm>...
            tm_node = well.find('.//Tm')
            if tm_node is not None:
                try:
                    tm_value = float(tm_node.text)
                except (ValueError, TypeError):
                    pass

            wells[well_pos] = {
                'well_position': well_pos,
                'sample_name': sample_name,
                'tm_value': tm_value,
                # Defaulting others for now
                'target_dye': 'SYBR', # Placeholder or extract from <Dye>
                'sample_role': 'Unknown'
            }
            
        return wells

    def _extract_melt_curves(self, z, well_map):
        """
        Attempts to find and parse melt curve data.
        """
        # Strategy 1: Look for known text-based data exports in the zip
        # Some systems export a 'processed_data.xml' or similar.
        
        # Searching for any XML that might look like data
        fallback_files = [f for f in z.namelist() if f.endswith('.xml') and ('data' in f.lower() or 'export' in f.lower())]
        
        # Strategy 2: Check for binary files in apldbio/sds/quant/
        # (This is a placeholder for complex binary parsing)
        quant_files = [f for f in z.namelist() if f.startswith('apldbio/sds/quant/') and f.endswith('.bin')]
        
        data_found = []

        if quant_files:
            logger.info(f"Found {len(quant_files)} binary quant files. Attempting simplified binary read...")
            # NOTE: Real EDS binary parsing requires a specific proprietary spec. 
            # We will attempt to see if we can find floating point arrays, but this is brittle.
            # If this fails or is not implemented, we move to XML fallback.
            
            # For this exercise, we will assume we cannot reliably parse the proprietary binary 
            # without the specific schema (Big Endian vs Little Endian, headers, etc.).
            # We will log this limitation.
            logger.warning("Proprietary binary format detected. Direct parsing without spec is risky.")
            
            # If you know the format (e.g., contiguous floats), you could do:
            # data = z.read(quant_files[0])
            # floats = struct.unpack(f'{len(data)//4}f', data)
            
        # Strategy 3: XML Fallback (Preferred if binary parser unavailable)
        # Often "experiment_data.xml" or similar exists if the user checked "Export"
        # For the purpose of this script, we'll simulate finding data if we have well info,
        # OR parse a specific XML if found.
        
        # If no data found, return structure with empty arrays for now, 
        # so the pipeline doesn't crash.
        
        logger.info("Generating data structure for found wells (Data parsing is placeholder without valid source file).")
        
        for pos, well_info in well_map.items():
            # In a real scenario, we would populate these from the file
            data_found.append({
                'well_position': pos,
                'sample_name': well_info.get('sample_name'),
                'temperature_data': [],    # Placeholder: would be List[float]
                'fluorescence_data': []    # Placeholder: would be List[float]
            })
            
        return data_found

if __name__ == "__main__":
    # Test with a dummy path (will fail gracefully)
    parser = EdsParser("test.eds")
    print("Parser initialized. Call .parse() to run.")
