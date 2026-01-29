import zipfile
import xml.etree.ElementTree as ET
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EdsParser:
    def __init__(self, file_path):
        self.file_path = file_path

    def parse(self):
        """
        Main method to parse the EDS file.
        Returns a dictionary containing metadata, samples, and melt curve data.
        """
        results = {
            "metadata": {},
            "samples": {}, 
            "wells": {},
            "melt_curves": []
        }

        try:
            with zipfile.ZipFile(self.file_path, 'r') as z:
                # 1. Metadata (Run Name) from experiment.xml
                # This is still the most reliable place for high-level run info
                if "apldbio/sds/experiment.xml" in z.namelist():
                    with z.open("apldbio/sds/experiment.xml") as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        self._strip_namespaces(root)
                        results["metadata"] = self._extract_metadata(root)
                else:
                    results["metadata"] = {"run_name": "Unknown", "instrument_serial": "Unknown"}

                # 2. Main Data Parsing from analysis_result.txt
                # This file contains the Wells, Samples, Tm, and Curve Data all in one text table
                if "apldbio/sds/analysis_result.txt" in z.namelist():
                    with z.open("apldbio/sds/analysis_result.txt") as f:
                        # Decode bytes to string
                        content = f.read().decode('utf-8', errors='replace')
                        self._parse_analysis_result(content, results)
                else:
                    logger.error("apldbio/sds/analysis_result.txt not found.")
                    return None

        except zipfile.BadZipFile:
            logger.error(f"Error: {self.file_path} is not a valid zip file.")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return None

        return results

    def _strip_namespaces(self, element):
        for elem in element.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

    def _extract_metadata(self, root):
        metadata = {}
        metadata['run_name'] = root.findtext('.//Name')
        metadata['instrument_serial'] = root.findtext('.//InstrumentSerialNumber')
        metadata['run_start_time'] = root.findtext('.//RunStarted')
        return metadata

    def _index_to_position(self, index):
        """
        Converts 0-based well index to A01 format.
        Assumes standard 96-well row-major layout (12 columns).
        """
        try:
            idx = int(index)
            row = idx // 12
            col = idx % 12
            row_char = chr(65 + row)
            return f"{row_char}{col+1:02d}"
        except:
            return f"Idx_{index}"

    def _parse_analysis_result(self, content, results):
        """
        Parses the tab-separated analysis_result.txt file.
        Updates results['wells'], results['samples'], and results['melt_curves'].
        """
        lines = content.splitlines()
        
        current_well_id = None
        current_sample = None
        current_tm = None
        
        # Helper to clean and split lines
        def parse_floats(line_str):
            parts = line_str.strip().split('\t')
            # First part is label (e.g., "Sample Temperatures"), rest are data
            data = []
            for p in parts[1:]:
                try:
                    val = float(p.strip())
                    data.append(val)
                except ValueError:
                    continue
            return data

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            parts = line.split('\t')
            
            # Check if line starts with a number (Well Index)
            # Format: Well <tab> Sample Name <tab> ...
            if parts[0].isdigit():
                current_well_id = parts[0]
                well_pos = self._index_to_position(current_well_id)
                
                # Sample Name is usually 2nd column
                sample_name = parts[1] if len(parts) > 1 else "Unknown"
                
                # Tm is usually the last column(s). It might be comma separated if multiple peaks.
                # Example: "49.141586,73.766335"
                tm_str = parts[-1]
                tm_value = None
                try:
                    # Take the first Tm if multiple
                    tm_value = float(tm_str.split(',')[0])
                except ValueError:
                    tm_value = None

                current_sample = sample_name
                current_tm = tm_value
                
                # Add to Samples map
                # We use sample name as ID since we don't have a better one here
                results['samples'][sample_name] = {'name': sample_name, 'description': ''}
                
                # Add to Wells map
                results['wells'][well_pos] = {
                    'well_position': well_pos,
                    'sample_name': sample_name,
                    'tm_value': tm_value,
                    'target_dye': 'SYBR', # Defaulting
                    'sample_role': 'Unknown'
                }
                
                # We expect the NEXT line to be 'Sample Temperatures'
                # and the one AFTER to be 'Rn values'
                # We will look ahead safely
                if i + 2 < len(lines):
                    temp_line = lines[i+1]
                    fluor_line = lines[i+2]
                    
                    if "Sample Temperatures" in temp_line and "Rn values" in fluor_line:
                        temps = parse_floats(temp_line)
                        fluors = parse_floats(fluor_line)
                        
                        if temps and fluors:
                            results['melt_curves'].append({
                                'well_position': well_pos,
                                'sample_name': sample_name,
                                'temperature_data': temps,
                                'fluorescence_data': fluors
                            })

if __name__ == "__main__":
    pass
