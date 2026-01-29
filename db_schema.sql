-- Differential Scanning Fluorimetry (DSF) Data Schema
-- Optimized for efficient remote querying via Tailscale by storing raw curve data in arrays.

-- Table: experiments
-- Stores metadata about the experimental run.
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id SERIAL PRIMARY KEY,
    run_name TEXT,
    run_start_time TIMESTAMP WITH TIME ZONE,
    instrument_serial TEXT,
    file_name TEXT UNIQUE NOT NULL
);

-- Table: samples
-- Stores unique sample definitions.
CREATE TABLE IF NOT EXISTS samples (
    sample_id SERIAL PRIMARY KEY,
    sample_name TEXT UNIQUE NOT NULL,
    description TEXT
);

-- Table: wells
-- Represents a specific well in an experiment, linking sample and experimental conditions.
-- well_id is the primary key used to link to curve data.
CREATE TABLE IF NOT EXISTS wells (
    well_id SERIAL PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    sample_id INTEGER REFERENCES samples(sample_id) ON DELETE SET NULL,
    well_position VARCHAR(10) NOT NULL, -- e.g., 'A01'
    target_dye TEXT,
    sample_role TEXT, -- e.g., 'Unknown', 'Standard', 'NTC'
    tm_value DOUBLE PRECISION, -- Melting Temperature
    -- Ensure a well position is unique for a given dye in an experiment
    UNIQUE (experiment_id, well_position, target_dye)
);

-- Table: melt_curves
-- Stores the high-volume raw data.
-- Uses arrays (FLOAT[]) for temperature and fluorescence to minimize row count and overhead.
CREATE TABLE IF NOT EXISTS melt_curves (
    curve_id SERIAL PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    well_id INTEGER NOT NULL REFERENCES wells(well_id) ON DELETE CASCADE,
    temperature_data DOUBLE PRECISION[] NOT NULL,
    fluorescence_data DOUBLE PRECISION[] NOT NULL,
    UNIQUE (well_id) -- One curve per defined well entry
);

-- Index optimization for common lookups
CREATE INDEX IF NOT EXISTS idx_wells_experiment_id ON wells(experiment_id);
CREATE INDEX IF NOT EXISTS idx_wells_sample_id ON wells(sample_id);
CREATE INDEX IF NOT EXISTS idx_melt_curves_well_id ON melt_curves(well_id);
CREATE INDEX IF NOT EXISTS idx_melt_curves_experiment_id ON melt_curves(experiment_id);
