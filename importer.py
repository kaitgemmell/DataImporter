import os
import glob
import psycopg2
from psycopg2 import sql
import logging
from tqdm import tqdm
from eds_parser import EdsParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("importer.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database Configuration
# Update these with your specific connection details or use environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_PORT = os.getenv("DB_PORT", "5433")

DATA_DIR = "./DataFiles"

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def experiment_exists(cursor, file_name, run_name):
    """Checks if an experiment with the given filename or run name already exists."""
    query = "SELECT 1 FROM experiments WHERE file_name = %s OR run_name = %s"
    cursor.execute(query, (file_name, run_name))
    return cursor.fetchone() is not None

def get_or_create_sample(cursor, sample_name, description=None):
    """
    Retrieves a sample_id for a given sample_name. 
    Creates the sample if it does not exist.
    """
    if not sample_name:
        return None
        
    # Check if exists
    cursor.execute("SELECT sample_id FROM samples WHERE sample_name = %s", (sample_name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        # Insert new
        cursor.execute(
            "INSERT INTO samples (sample_name, description) VALUES (%s, %s) RETURNING sample_id",
            (sample_name, description)
        )
        return cursor.fetchone()[0]

def process_file(file_path, conn):
    """Parses a single .eds file and inserts data into the database."""
    file_name = os.path.basename(file_path)
    
    # 1. Parse Data
    parser = EdsParser(file_path)
    data = parser.parse()
    
    if not data:
        logger.warning(f"Skipping {file_name}: Parsing failed.")
        return False

    metadata = data['metadata']
    wells_data = data['wells']
    melt_curves = data['melt_curves']
    
    # Organize melt curves by well_position for easy lookup
    # Structure: {'A01': {'temperature_data': [], 'fluorescence_data': []}, ...}
    curves_map = {c['well_position']: c for c in melt_curves}

    try:
        with conn.cursor() as cursor:
            # 2. Check for Duplicates
            if experiment_exists(cursor, file_name, metadata.get('run_name')):
                logger.info(f"Skipping {file_name}: Already exists in database.")
                return False

            # 3. Insert Experiment
            logger.info(f"Inserting experiment: {metadata.get('run_name', 'Unknown')}")
            cursor.execute(
                """
                INSERT INTO experiments (run_name, run_start_time, instrument_serial, file_name)
                VALUES (%s, %s, %s, %s)
                RETURNING experiment_id
                """,
                (metadata.get('run_name'), metadata.get('run_start_time'), metadata.get('instrument_serial'), file_name)
            )
            experiment_id = cursor.fetchone()[0]

            # 4. Process Wells & Samples
            for well_pos, well_info in wells_data.items():
                
                # Handle Sample
                sample_name = well_info.get('sample_name')
                # If sample name is missing, we might use "Unknown" or skip sample linking
                if not sample_name:
                    sample_name = f"Unknown_Sample_{experiment_id}_{well_pos}"
                
                sample_id = get_or_create_sample(cursor, sample_name)

                # Insert Well
                cursor.execute(
                    """
                    INSERT INTO wells (experiment_id, sample_id, well_position, target_dye, sample_role, tm_value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING well_id
                    """,
                    (
                        experiment_id, 
                        sample_id, 
                        well_pos, 
                        well_info.get('target_dye'), 
                        well_info.get('sample_role'), 
                        well_info.get('tm_value')
                    )
                )
                well_id = cursor.fetchone()[0]

                # 5. Insert Melt Curve Data (if exists for this well)
                if well_pos in curves_map:
                    curve_data = curves_map[well_pos]
                    temp_data = curve_data.get('temperature_data', [])
                    fluor_data = curve_data.get('fluorescence_data', [])
                    
                    if temp_data and fluor_data:
                        cursor.execute(
                            """
                            INSERT INTO melt_curves (experiment_id, well_id, temperature_data, fluorescence_data)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (experiment_id, well_id, temp_data, fluor_data)
                        )
            
            conn.commit()
            return True

    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing {file_name}: {e}")
        return False

def main():
    # check if directory exists
    if not os.path.exists(DATA_DIR):
        logger.error(f"Data directory not found: {DATA_DIR}")
        return

    eds_files = glob.glob(os.path.join(DATA_DIR, "*.eds"))
    
    if not eds_files:
        logger.info("No .eds files found in DataFiles directory.")
        return

    logger.info(f"Found {len(eds_files)} files to process.")

    try:
        conn = get_db_connection()
    except Exception:
        return

    # Process files with progress bar
    with tqdm(total=len(eds_files), desc="Processing EDS Files") as pbar:
        for file_path in eds_files:
            process_file(file_path, conn)
            pbar.update(1)

    conn.close()
    logger.info("Import process completed.")

if __name__ == "__main__":
    main()
