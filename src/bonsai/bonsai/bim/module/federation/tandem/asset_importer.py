"""
Digital Twin - Asset Importer
Extract equipment data from IFC models and populate asset registry

Supports:
- IfcDistributionElement (MEP equipment)
- IfcFurnishingElement
- IfcTransportElement
- Custom equipment types
"""

import ifcopenshell
import ifcopenshell.util.element
from typing import Optional, List, Dict, Any
from .asset_registry import AssetRegistry


class AssetImporter:
    """Import equipment from IFC models into asset registry"""

    # IFC classes considered as assets
    ASSET_CLASSES = [
        # HVAC
        'IfcAirTerminal',
        'IfcAirToAirHeatRecovery',
        'IfcBoiler',
        'IfcChiller',
        'IfcCoil',
        'IfcCondenser',
        'IfcCooledBeam',
        'IfcCoolingTower',
        'IfcDamper',
        'IfcDuctSilencer',
        'IfcFan',
        'IfcFilter',
        'IfcHeatExchanger',
        'IfcHumidifier',
        'IfcAirHandlingUnit',
        'IfcVibrationIsolator',

        # Plumbing
        'IfcPump',
        'IfcTank',
        'IfcValve',
        'IfcWasteTerminal',
        'IfcSanitaryTerminal',

        # Electrical
        'IfcElectricAppliance',
        'IfcElectricDistributionBoard',
        'IfcElectricFlowStorageDevice',
        'IfcElectricGenerator',
        'IfcElectricMotor',
        'IfcElectricTimeControl',
        'IfcLamp',
        'IfcLightFixture',
        'IfcMotorConnection',
        'IfcOutlet',
        'IfcSwitchingDevice',
        'IfcTransformer',

        # Fire Protection
        'IfcFireSuppressionTerminal',
        'IfcAlarm',

        # Building Equipment
        'IfcUnitaryEquipment',
        'IfcMedicalDevice',
        'IfcCommunicationsAppliance',
        'IfcAudioVisualAppliance',

        # Transport
        'IfcTransportElement',
    ]

    # Discipline mapping
    DISCIPLINE_MAP = {
        # HVAC/ACMV
        'IfcAirTerminal': 'ACMV',
        'IfcAirToAirHeatRecovery': 'ACMV',
        'IfcBoiler': 'ACMV',
        'IfcChiller': 'ACMV',
        'IfcCoil': 'ACMV',
        'IfcCondenser': 'ACMV',
        'IfcCooledBeam': 'ACMV',
        'IfcCoolingTower': 'ACMV',
        'IfcDamper': 'ACMV',
        'IfcDuctSilencer': 'ACMV',
        'IfcFan': 'ACMV',
        'IfcFilter': 'ACMV',
        'IfcHeatExchanger': 'ACMV',
        'IfcHumidifier': 'ACMV',
        'IfcAirHandlingUnit': 'ACMV',
        'IfcVibrationIsolator': 'ACMV',

        # Plumbing
        'IfcPump': 'PLB',
        'IfcTank': 'PLB',
        'IfcValve': 'PLB',
        'IfcWasteTerminal': 'PLB',
        'IfcSanitaryTerminal': 'PLB',

        # Electrical
        'IfcElectricAppliance': 'ELEC',
        'IfcElectricDistributionBoard': 'ELEC',
        'IfcElectricFlowStorageDevice': 'ELEC',
        'IfcElectricGenerator': 'ELEC',
        'IfcElectricMotor': 'ELEC',
        'IfcElectricTimeControl': 'ELEC',
        'IfcLamp': 'ELEC',
        'IfcLightFixture': 'ELEC',
        'IfcMotorConnection': 'ELEC',
        'IfcOutlet': 'ELEC',
        'IfcSwitchingDevice': 'ELEC',
        'IfcTransformer': 'ELEC',

        # Fire Protection
        'IfcFireSuppressionTerminal': 'FP',
        'IfcAlarm': 'FP',
    }

    def __init__(self, registry: AssetRegistry):
        """
        Initialize importer

        Args:
            registry: AssetRegistry instance
        """
        self.registry = registry

    def import_from_ifc(self, ifc_path: str,
                       discipline_filter: Optional[List[str]] = None,
                       progress_callback=None) -> Dict[str, Any]:
        """
        Import assets from IFC file

        Args:
            ifc_path: Path to IFC file
            discipline_filter: Only import these disciplines (e.g., ['ACMV', 'ELEC'])
            progress_callback: Optional callback(current, total, message)

        Returns:
            Import statistics
        """
        ifc_file = ifcopenshell.open(ifc_path)

        stats = {
            'total_scanned': 0,
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'by_discipline': {},
            'by_ifc_class': {}
        }

        # Get all equipment elements
        elements = []
        for ifc_class in self.ASSET_CLASSES:
            try:
                elements.extend(ifc_file.by_type(ifc_class))
            except:
                pass  # Class not in schema

        stats['total_scanned'] = len(elements)

        for idx, element in enumerate(elements):
            if progress_callback:
                progress_callback(idx + 1, len(elements), f"Processing {element.is_a()}")

            try:
                # Extract asset data
                asset_data = self._extract_asset_data(element)

                # Apply discipline filter
                if discipline_filter:
                    if asset_data.get('discipline') not in discipline_filter:
                        stats['skipped'] += 1
                        continue

                # Create asset
                self.registry.create_asset(asset_data)

                # Extract and add custom properties
                self._import_properties(element, asset_data['guid'])

                # Update stats
                stats['imported'] += 1

                discipline = asset_data.get('discipline', 'Unknown')
                stats['by_discipline'][discipline] = stats['by_discipline'].get(discipline, 0) + 1

                ifc_class = asset_data['ifc_class']
                stats['by_ifc_class'][ifc_class] = stats['by_ifc_class'].get(ifc_class, 0) + 1

            except Exception as e:
                stats['errors'] += 1
                print(f"Error importing {element.GlobalId}: {e}")

        return stats

    def _extract_asset_data(self, element) -> Dict[str, Any]:
        """Extract core asset data from IFC element"""

        asset_data = {
            'guid': element.GlobalId,
            'name': element.Name or f"{element.is_a()}",
            'ifc_class': element.is_a(),
            'discipline': self.DISCIPLINE_MAP.get(element.is_a(), 'Other'),
        }

        # Get type information
        if hasattr(element, 'ObjectType') and element.ObjectType:
            asset_data['ifc_type'] = element.ObjectType

        # Get location (storey)
        storey = self._get_storey(element)
        if storey:
            asset_data['storey'] = storey.Name if storey.Name else 'Unknown'

        # Get space
        space = self._get_space(element)
        if space:
            asset_data['space'] = space.LongName or space.Name if space.Name else None

        # Extract property sets
        psets = ifcopenshell.util.element.get_psets(element)

        # Look for common manufacturer/model properties
        for pset_name, props in psets.items():
            if 'Manufacturer' in props:
                asset_data['manufacturer'] = props['Manufacturer']
            if 'Model' in props or 'ModelReference' in props:
                asset_data['model'] = props.get('Model') or props.get('ModelReference')
            if 'SerialNumber' in props:
                asset_data['serial_number'] = props['SerialNumber']
            if 'InstallationDate' in props:
                asset_data['install_date'] = str(props['InstallationDate'])
            if 'WarrantyStartDate' in props:
                asset_data['warranty_start'] = str(props['WarrantyStartDate'])
            if 'WarrantyDurationMonths' in props or 'WarrantyDuration' in props:
                duration = props.get('WarrantyDurationMonths') or props.get('WarrantyDuration')
                if duration:
                    asset_data['warranty_duration_months'] = int(duration)
            if 'ExpectedLifespan' in props or 'ServiceLifeYears' in props:
                lifespan = props.get('ExpectedLifespan') or props.get('ServiceLifeYears')
                if lifespan:
                    asset_data['expected_lifespan_years'] = int(lifespan)
            if 'ReplacementCost' in props:
                asset_data['replacement_cost'] = float(props['ReplacementCost'])

        # Look for capacity/rating
        capacity_props = ['NominalCapacity', 'Capacity', 'FlowRate', 'Power', 'Rating']
        for prop_name in capacity_props:
            for pset_name, props in psets.items():
                if prop_name in props:
                    value = props[prop_name]
                    if value:
                        asset_data['capacity'] = str(value)
                        break

        return asset_data

    def _import_properties(self, element, asset_guid: str):
        """Import all IFC properties as custom asset properties"""
        psets = ifcopenshell.util.element.get_psets(element)

        # Standard fields that are already in main table
        skip_props = {
            'GlobalId', 'Name', 'ObjectType', 'Manufacturer', 'Model',
            'ModelReference', 'SerialNumber', 'InstallationDate',
            'WarrantyStartDate', 'WarrantyDuration', 'WarrantyDurationMonths',
            'ExpectedLifespan', 'ServiceLifeYears', 'ReplacementCost',
            'NominalCapacity', 'Capacity', 'FlowRate', 'Power', 'Rating'
        }

        for pset_name, props in psets.items():
            for prop_name, prop_value in props.items():
                if prop_name in skip_props or prop_value is None:
                    continue

                # Determine property type
                prop_type = 'string'
                if isinstance(prop_value, bool):
                    prop_type = 'boolean'
                    prop_value = str(prop_value)
                elif isinstance(prop_value, (int, float)):
                    prop_type = 'number'
                    prop_value = str(prop_value)
                else:
                    prop_value = str(prop_value)

                # Store with pset prefix
                full_name = f"{pset_name}.{prop_name}"

                try:
                    self.registry.add_property(
                        asset_guid,
                        full_name,
                        prop_value,
                        prop_type
                    )
                except Exception as e:
                    print(f"Warning: Could not add property {full_name}: {e}")

    def _get_storey(self, element):
        """Get building storey for element"""
        # Try spatial containment
        if hasattr(element, 'ContainedInStructure'):
            for rel in element.ContainedInStructure:
                structure = rel.RelatingStructure
                if structure.is_a('IfcBuildingStorey'):
                    return structure
                elif structure.is_a('IfcSpace'):
                    # Try to get storey from space
                    if hasattr(structure, 'Decomposes'):
                        for decomp in structure.Decomposes:
                            if decomp.is_a('IfcRelAggregates'):
                                parent = decomp.RelatingObject
                                if parent.is_a('IfcBuildingStorey'):
                                    return parent
        return None

    def _get_space(self, element):
        """Get space for element"""
        if hasattr(element, 'ContainedInStructure'):
            for rel in element.ContainedInStructure:
                structure = rel.RelatingStructure
                if structure.is_a('IfcSpace'):
                    return structure
        return None

    def import_from_blend(self, progress_callback=None) -> Dict[str, Any]:
        """
        Import assets from currently loaded Blender/IFC model

        Args:
            progress_callback: Optional callback(current, total, message)

        Returns:
            Import statistics
        """
        import bpy
        import bonsai.tool as tool

        ifc_file = tool.Ifc.get()
        if not ifc_file:
            raise ValueError("No IFC file loaded in Blender")

        stats = {
            'total_scanned': 0,
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'by_discipline': {},
            'by_ifc_class': {}
        }

        # Get all equipment elements
        elements = []
        for ifc_class in self.ASSET_CLASSES:
            try:
                elements.extend(ifc_file.by_type(ifc_class))
            except:
                pass

        stats['total_scanned'] = len(elements)

        for idx, element in enumerate(elements):
            if progress_callback:
                progress_callback(idx + 1, len(elements), f"Processing {element.is_a()}")

            try:
                # Check if already exists
                existing = self.registry.get_asset(element.GlobalId)
                if existing:
                    stats['skipped'] += 1
                    continue

                # Extract and create
                asset_data = self._extract_asset_data(element)
                self.registry.create_asset(asset_data)
                self._import_properties(element, asset_data['guid'])

                stats['imported'] += 1

                discipline = asset_data.get('discipline', 'Unknown')
                stats['by_discipline'][discipline] = stats['by_discipline'].get(discipline, 0) + 1

                ifc_class = asset_data['ifc_class']
                stats['by_ifc_class'][ifc_class] = stats['by_ifc_class'].get(ifc_class, 0) + 1

            except Exception as e:
                stats['errors'] += 1
                print(f"Error importing {element.GlobalId}: {e}")

        return stats
