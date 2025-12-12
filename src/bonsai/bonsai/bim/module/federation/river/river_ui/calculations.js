/**
 * Klang River Project - Calculation Engine
 * Based on Coastal Oasis Sungai Klang Project Data
 *
 * Real Project Parameters:
 * - 56km river system
 * - 40 boom sites
 * - 2,000-3,000 MT/day waste interception
 * - 30% plastic / 70% organic composition
 * - 9,943 hectares mangrove restoration
 */

const PROJECT_CONSTANTS = {
    // River System
    RIVER_LENGTH_KM: 56,
    BOOM_SITES: 40,
    STRETCH_LENGTH_KM: 1.4, // 56km / 40 sites

    // Waste Interception
    DAILY_WASTE_MIN_MT: 2000,
    DAILY_WASTE_MAX_MT: 3000,
    PLASTIC_FRACTION: 0.30,
    ORGANIC_FRACTION: 0.70,

    // Dredging (industry standard for urban rivers)
    AVG_RIVER_WIDTH_M: 45,
    AVG_DEPTH_CURRENT_M: 2.5,
    AVG_DEPTH_TARGET_M: 4.0,
    SEDIMENTATION_RATE_M3_PER_KM_YEAR: 1200, // tropical urban river

    // Material Processing
    BIOCHAR_YIELD: 0.25, // 25% of dried organic mass
    PYROLYSIS_OIL_YIELD: 0.50, // 50% of plastic to oil
    RDF_FRACTION: 0.40, // 40% to RDF

    // Carbon Sequestration
    BIOCHAR_CO2_PER_TONNE: 2.75, // tCO2e
    MANGROVE_CO2_PER_HA_YEAR: 10.0, // tCO2e/ha/year (mid-range)
    MANGROVE_RESTORATION_HA: 9943,

    // Revenue (RM per unit)
    PRICE_PLASTIC_HIGH_GRADE: 0.55, // RM/kg
    PRICE_PLASTIC_MIXED: 0.25, // RM/kg
    PRICE_PYRO_OIL: 550, // RM/tonne
    PRICE_RDF: 175, // RM/tonne
    PRICE_BIOCHAR: 1600, // RM/tonne
    PRICE_CARBON_CREDIT_BIOCHAR: 740, // RM/tCO2e
    PRICE_CARBON_CREDIT_MANGROVE: 50, // RM/tCO2e

    // Workload (person-days per unit)
    LABOR_DREDGING_PER_1000M3: 120,
    LABOR_BOOM_OPERATION_PER_SITE_DAY: 3,
    LABOR_MRF_PER_100MT: 8,
    LABOR_MANGROVE_PER_HA: 25,

    // Equipment rates
    EXCAVATOR_PRODUCTIVITY_M3_PER_DAY: 250,
    BARGE_CAPACITY_M3: 100,
};

/**
 * Calculate dredging volume for river stretches
 */
function calculateDredgingVolume(stretchKm = null) {
    const lengthKm = stretchKm || PROJECT_CONSTANTS.RIVER_LENGTH_KM;
    const lengthM = lengthKm * 1000;

    // Volume = length × width × depth difference
    const depthDiff = PROJECT_CONSTANTS.AVG_DEPTH_TARGET_M - PROJECT_CONSTANTS.AVG_DEPTH_CURRENT_M;
    const volume_m3 = lengthM * PROJECT_CONSTANTS.AVG_RIVER_WIDTH_M * depthDiff;

    // Annual sedimentation maintenance
    const annual_maintenance_m3 = lengthKm * PROJECT_CONSTANTS.SEDIMENTATION_RATE_M3_PER_KM_YEAR;

    // Labor and equipment
    const excavator_days = volume_m3 / PROJECT_CONSTANTS.EXCAVATOR_PRODUCTIVITY_M3_PER_DAY;
    const barge_trips = volume_m3 / PROJECT_CONSTANTS.BARGE_CAPACITY_M3;
    const labor_person_days = (volume_m3 / 1000) * PROJECT_CONSTANTS.LABOR_DREDGING_PER_1000M3;

    return {
        initial_volume_m3: Math.round(volume_m3),
        annual_maintenance_m3: Math.round(annual_maintenance_m3),
        excavator_days: Math.round(excavator_days),
        barge_trips: Math.round(barge_trips),
        labor_person_days: Math.round(labor_person_days),
        stretch_km: lengthKm,
        avg_width_m: PROJECT_CONSTANTS.AVG_RIVER_WIDTH_M,
        depth_diff_m: depthDiff
    };
}

/**
 * Calculate waste interception and processing capacity
 */
function calculateWasteProcessing(dailyWasteMT = null, daysPerYear = 300) {
    const waste_mt_day = dailyWasteMT ||
        (PROJECT_CONSTANTS.DAILY_WASTE_MIN_MT + PROJECT_CONSTANTS.DAILY_WASTE_MAX_MT) / 2;

    // Annual volumes
    const annual_waste_mt = waste_mt_day * daysPerYear;
    const annual_plastic_mt = annual_waste_mt * PROJECT_CONSTANTS.PLASTIC_FRACTION;
    const annual_organic_mt = annual_waste_mt * PROJECT_CONSTANTS.ORGANIC_FRACTION;

    // Processing outputs
    const biochar_mt = annual_organic_mt * PROJECT_CONSTANTS.BIOCHAR_YIELD;
    const pyro_oil_mt = annual_plastic_mt * PROJECT_CONSTANTS.PYROLYSIS_OIL_YIELD;
    const rdf_mt = annual_plastic_mt * PROJECT_CONSTANTS.RDF_FRACTION;
    const high_grade_plastic_mt = annual_plastic_mt * 0.10; // 10% high grade

    // Revenue calculations
    const revenue_biochar = biochar_mt * PROJECT_CONSTANTS.PRICE_BIOCHAR;
    const revenue_pyro_oil = pyro_oil_mt * PROJECT_CONSTANTS.PRICE_PYRO_OIL;
    const revenue_rdf = rdf_mt * PROJECT_CONSTANTS.PRICE_RDF;
    const revenue_plastic = (high_grade_plastic_mt * 1000 * PROJECT_CONSTANTS.PRICE_PLASTIC_HIGH_GRADE) +
                           ((annual_plastic_mt - high_grade_plastic_mt) * 1000 * PROJECT_CONSTANTS.PRICE_PLASTIC_MIXED);

    const total_revenue = revenue_biochar + revenue_pyro_oil + revenue_rdf + revenue_plastic;

    // Labor
    const labor_boom_operation = PROJECT_CONSTANTS.BOOM_SITES *
                                 PROJECT_CONSTANTS.LABOR_BOOM_OPERATION_PER_SITE_DAY *
                                 daysPerYear;
    const labor_mrf = (annual_waste_mt / 100) * PROJECT_CONSTANTS.LABOR_MRF_PER_100MT;

    return {
        daily_waste_mt: waste_mt_day,
        annual_waste_mt: Math.round(annual_waste_mt),
        annual_plastic_mt: Math.round(annual_plastic_mt),
        annual_organic_mt: Math.round(annual_organic_mt),
        outputs: {
            biochar_mt: Math.round(biochar_mt),
            pyro_oil_mt: Math.round(pyro_oil_mt),
            rdf_mt: Math.round(rdf_mt),
            high_grade_plastic_mt: Math.round(high_grade_plastic_mt)
        },
        revenue_rm: {
            biochar: Math.round(revenue_biochar),
            pyro_oil: Math.round(revenue_pyro_oil),
            rdf: Math.round(revenue_rdf),
            plastic: Math.round(revenue_plastic),
            total: Math.round(total_revenue)
        },
        labor_person_days: {
            boom_operation: Math.round(labor_boom_operation),
            mrf_processing: Math.round(labor_mrf),
            total: Math.round(labor_boom_operation + labor_mrf)
        }
    };
}

/**
 * Calculate carbon sequestration and credits
 */
function calculateCarbonCredits() {
    const waste = calculateWasteProcessing();

    // Biochar carbon sequestration
    const biochar_co2_annual = waste.outputs.biochar_mt * PROJECT_CONSTANTS.BIOCHAR_CO2_PER_TONNE;
    const biochar_credit_revenue = biochar_co2_annual * PROJECT_CONSTANTS.PRICE_CARBON_CREDIT_BIOCHAR;

    // Mangrove carbon sequestration
    const mangrove_co2_annual = PROJECT_CONSTANTS.MANGROVE_RESTORATION_HA *
                                PROJECT_CONSTANTS.MANGROVE_CO2_PER_HA_YEAR;
    const mangrove_credit_revenue = mangrove_co2_annual * PROJECT_CONSTANTS.PRICE_CARBON_CREDIT_MANGROVE;

    const total_co2_sequestered = biochar_co2_annual + mangrove_co2_annual;
    const total_credit_revenue = biochar_credit_revenue + mangrove_credit_revenue;

    return {
        biochar: {
            co2_tonnes_year: Math.round(biochar_co2_annual),
            revenue_rm_year: Math.round(biochar_credit_revenue),
            registry: "Puro.Earth",
            price_per_tco2: PROJECT_CONSTANTS.PRICE_CARBON_CREDIT_BIOCHAR
        },
        mangrove: {
            co2_tonnes_year: Math.round(mangrove_co2_annual),
            revenue_rm_year: Math.round(mangrove_credit_revenue),
            area_ha: PROJECT_CONSTANTS.MANGROVE_RESTORATION_HA,
            registry: "Verra / Gold Standard",
            price_per_tco2: PROJECT_CONSTANTS.PRICE_CARBON_CREDIT_MANGROVE
        },
        total: {
            co2_tonnes_year: Math.round(total_co2_sequestered),
            revenue_rm_year: Math.round(total_credit_revenue)
        }
    };
}

/**
 * Calculate workload distribution by stretch
 * Divides 56km river into stretches with phased implementation
 */
function calculateWorkloadByStretch(numStretches = 40) {
    const stretchLength = PROJECT_CONSTANTS.RIVER_LENGTH_KM / numStretches;
    const stretches = [];

    // Per-stretch calculations
    for (let i = 0; i < numStretches; i++) {
        const dredging = calculateDredgingVolume(stretchLength);
        const boomSites = 1; // 1 boom site per stretch

        stretches.push({
            id: i + 1,
            name: `Stretch ${i + 1}`,
            km_start: Math.round(i * stretchLength * 10) / 10,
            km_end: Math.round((i + 1) * stretchLength * 10) / 10,
            boom_sites: boomSites,
            dredging_m3: dredging.initial_volume_m3,
            excavator_days: dredging.excavator_days,
            labor_days: dredging.labor_person_days,
            priority: i < 10 ? 'HIGH' : (i < 25 ? 'MEDIUM' : 'LOW'), // Front-load critical areas
            phase: Math.floor(i / 10) + 1 // 4 phases
        });
    }

    return stretches;
}

/**
 * Calculate workload distribution by discipline
 */
function calculateWorkloadByDiscipline() {
    const dredging = calculateDredgingVolume();
    const waste = calculateWasteProcessing();

    return [
        {
            discipline: 'Civil Engineering (Dredging)',
            scope: `${dredging.initial_volume_m3.toLocaleString()} m³ initial + ${dredging.annual_maintenance_m3.toLocaleString()} m³/year`,
            labor_days: dredging.labor_person_days,
            equipment: `${dredging.excavator_days} excavator-days, ${dredging.barge_trips} barge trips`,
            duration_months: Math.round(dredging.excavator_days / 30)
        },
        {
            discipline: 'Environmental (Boom Operations)',
            scope: `${PROJECT_CONSTANTS.BOOM_SITES} sites @ ${waste.daily_waste_mt} MT/day`,
            labor_days: waste.labor_person_days.boom_operation,
            equipment: '40 log boom systems, skimmers, cranes',
            duration_months: 12 // Ongoing operations
        },
        {
            discipline: 'Process Engineering (MRF/Pyrolysis)',
            scope: `${waste.annual_waste_mt.toLocaleString()} MT/year processing`,
            labor_days: waste.labor_person_days.mrf_processing,
            equipment: 'MRF facility, pyrolysis reactors, biochar kilns',
            duration_months: 12 // Ongoing operations
        },
        {
            discipline: 'Ecology (Mangrove Restoration)',
            scope: `${PROJECT_CONSTANTS.MANGROVE_RESTORATION_HA.toLocaleString()} hectares`,
            labor_days: PROJECT_CONSTANTS.MANGROVE_RESTORATION_HA * PROJECT_CONSTANTS.LABOR_MANGROVE_PER_HA,
            equipment: 'Planting boats, nursery facilities',
            duration_months: 36 // 3-year restoration program
        }
    ];
}

/**
 * Generate 4D schedule data (time-phased workload)
 */
function generate4DSchedule() {
    const startDate = new Date('2025-01-01');
    const stretches = calculateWorkloadByStretch();
    const schedule = [];

    // Phase 1: Months 1-6 (Stretches 1-10, HIGH priority)
    // Phase 2: Months 7-12 (Stretches 11-25, MEDIUM priority)
    // Phase 3: Months 13-24 (Stretches 26-40, LOW priority)
    // Phase 4: Ongoing operations (all stretches)

    stretches.forEach(stretch => {
        const phaseStartMonth = (stretch.phase - 1) * 6;
        const taskStart = new Date(startDate);
        taskStart.setMonth(taskStart.getMonth() + phaseStartMonth);

        const taskEnd = new Date(taskStart);
        taskEnd.setDate(taskEnd.getDate() + stretch.excavator_days);

        schedule.push({
            task_id: `DREDGE-${stretch.id}`,
            task_name: `Dredging ${stretch.name} (km ${stretch.km_start}-${stretch.km_end})`,
            discipline: 'Civil',
            start_date: taskStart.toISOString().split('T')[0],
            end_date: taskEnd.toISOString().split('T')[0],
            duration_days: stretch.excavator_days,
            workload_m3: stretch.dredging_m3,
            priority: stretch.priority,
            phase: stretch.phase,
            location: {
                km: (stretch.km_start + stretch.km_end) / 2,
                lat: 3.0 + (stretch.id * 0.01), // Mock coordinates along river
                lon: 101.4 + (stretch.id * 0.01)
            }
        });

        // Boom installation after dredging
        const boomStart = new Date(taskEnd);
        boomStart.setDate(boomStart.getDate() + 1);
        const boomEnd = new Date(boomStart);
        boomEnd.setDate(boomEnd.getDate() + 7);

        schedule.push({
            task_id: `BOOM-${stretch.id}`,
            task_name: `Install Boom Site ${stretch.id}`,
            discipline: 'Environmental',
            start_date: boomStart.toISOString().split('T')[0],
            end_date: boomEnd.toISOString().split('T')[0],
            duration_days: 7,
            priority: stretch.priority,
            phase: stretch.phase,
            location: {
                km: (stretch.km_start + stretch.km_end) / 2,
                lat: 3.0 + (stretch.id * 0.01),
                lon: 101.4 + (stretch.id * 0.01)
            }
        });
    });

    return schedule;
}

/**
 * Generate comprehensive project summary for dashboard
 */
function generateProjectSummary() {
    const dredging = calculateDredgingVolume();
    const waste = calculateWasteProcessing();
    const carbon = calculateCarbonCredits();
    const disciplines = calculateWorkloadByDiscipline();

    const total_revenue = waste.revenue_rm.total + carbon.total.revenue_rm_year;

    return {
        project: {
            name: 'Coastal Oasis Sungai Klang',
            location: 'Selangor, Malaysia',
            river_length_km: PROJECT_CONSTANTS.RIVER_LENGTH_KM,
            boom_sites: PROJECT_CONSTANTS.BOOM_SITES,
            mangrove_restoration_ha: PROJECT_CONSTANTS.MANGROVE_RESTORATION_HA
        },
        scope: {
            dredging: {
                initial_m3: dredging.initial_volume_m3,
                annual_maintenance_m3: dredging.annual_maintenance_m3,
                excavator_days: dredging.excavator_days
            },
            waste_processing: {
                daily_mt: waste.daily_waste_mt,
                annual_mt: waste.annual_waste_mt,
                plastic_mt: waste.annual_plastic_mt,
                organic_mt: waste.annual_organic_mt
            },
            carbon_sequestration: {
                total_co2_tonnes_year: carbon.total.co2_tonnes_year,
                biochar_co2: carbon.biochar.co2_tonnes_year,
                mangrove_co2: carbon.mangrove.co2_tonnes_year
            }
        },
        revenue: {
            material_processing_rm: waste.revenue_rm.total,
            carbon_credits_rm: carbon.total.revenue_rm_year,
            total_annual_rm: total_revenue,
            breakdown: {
                biochar: waste.revenue_rm.biochar + carbon.biochar.revenue_rm_year,
                pyro_oil: waste.revenue_rm.pyro_oil,
                rdf: waste.revenue_rm.rdf,
                plastic: waste.revenue_rm.plastic,
                mangrove_credits: carbon.mangrove.revenue_rm_year
            }
        },
        workload: {
            disciplines: disciplines,
            total_labor_days: disciplines.reduce((sum, d) => sum + d.labor_days, 0)
        }
    };
}

// Export functions for use in viewer
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        PROJECT_CONSTANTS,
        calculateDredgingVolume,
        calculateWasteProcessing,
        calculateCarbonCredits,
        calculateWorkloadByStretch,
        calculateWorkloadByDiscipline,
        generate4DSchedule,
        generateProjectSummary
    };
}
