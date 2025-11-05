"""
BCF 2.1 XML Generator

Generates BIM Collaboration Format (BCF) 2.1 compliant XML files from clash detection data.
BCF is the industry standard for issue tracking in BIM coordination workflows.

References:
- BCF 2.1 Specification: https://github.com/buildingSMART/BCF-XML
- Format: ZIP archive containing markup.bcf, project.bcfp, and topic folders with XML + snapshots
"""

import sqlite3
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import zipfile
import io


class BCFGenerator:
    """
    Generates BCF 2.1 format files from clash detection database.

    BCF Structure:
    - bcf.version (version marker)
    - project.bcfp (project metadata)
    - markup.bcf (topics index)
    - {topic_guid}/
      - markup.bcf (topic details, comments, viewpoints)
      - viewpoint.bcfv (3D camera position)
      - snapshot.png (rendered image)
    """

    BCF_VERSION = "2.1"

    def __init__(self, database_path: str):
        """
        Initialize BCF generator.

        Args:
            database_path: Path to clash detection database
        """
        self.database_path = database_path
        self.project_name = "BIM Coordination"
        self.author = "Bonsai BIM"

    def generate_bcf_zip(
        self,
        output_path: str,
        clash_ids: Optional[List[int]] = None,
        include_resolved: bool = False,
        viewpoints: Optional[Dict[int, Dict]] = None,
        snapshots: Optional[Dict[int, bytes]] = None
    ) -> Tuple[bool, str]:
        """
        Generate complete BCF ZIP file from clash database.

        Args:
            output_path: Path for output BCF file (*.bcfzip)
            clash_ids: Specific clash IDs to export (None = all clashes)
            include_resolved: Include resolved clashes in export
            viewpoints: Dict mapping clash_id to viewpoint data (camera, target, up)
            snapshots: Dict mapping clash_id to PNG image bytes

        Returns:
            (success: bool, message: str)
        """
        try:
            # Fetch clashes from database
            clashes = self._fetch_clashes(clash_ids, include_resolved)

            if not clashes:
                return False, "No clashes found to export"

            # Create ZIP file in memory
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as bcf_zip:
                # Add BCF version marker
                bcf_zip.writestr('bcf.version', self._generate_version_xml())

                # Add project metadata
                bcf_zip.writestr('project.bcfp', self._generate_project_xml())

                # Process each clash as a BCF topic
                for clash in clashes:
                    topic_guid = str(uuid.uuid4())
                    clash_id = clash['clash_id']

                    # Generate markup for this topic
                    markup_xml = self._generate_markup_xml(clash, topic_guid)
                    bcf_zip.writestr(f'{topic_guid}/markup.bcf', markup_xml)

                    # Add viewpoint if available
                    if viewpoints and clash_id in viewpoints:
                        viewpoint_xml = self._generate_viewpoint_xml(
                            viewpoints[clash_id]
                        )
                        bcf_zip.writestr(f'{topic_guid}/viewpoint.bcfv', viewpoint_xml)

                    # Add snapshot if available
                    if snapshots and clash_id in snapshots:
                        bcf_zip.writestr(
                            f'{topic_guid}/snapshot.png',
                            snapshots[clash_id]
                        )

            # Write to file
            with open(output_path, 'wb') as f:
                f.write(zip_buffer.getvalue())

            return True, f"BCF exported successfully: {len(clashes)} topics"

        except Exception as e:
            return False, f"BCF generation failed: {str(e)}"

    def _fetch_clashes(
        self,
        clash_ids: Optional[List[int]],
        include_resolved: bool
    ) -> List[Dict]:
        """Fetch clash data from database."""
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = """
            SELECT
                cs.clash_id,
                cs.guid_a,
                cs.guid_b,
                cs.name_a,
                cs.name_b,
                cs.ifc_class_a,
                cs.ifc_class_b,
                cs.discipline_a,
                cs.discipline_b,
                cs.status,
                cs.assigned_to,
                cs.comment,
                cs.distance,
                cs.date_created,
                cs.date_modified
            FROM clash_status cs
            WHERE cs.is_ignored = 0
        """

        params = []

        if clash_ids:
            placeholders = ','.join('?' * len(clash_ids))
            query += f" AND cs.clash_id IN ({placeholders})"
            params.extend(clash_ids)

        if not include_resolved:
            query += " AND cs.status != 'RESOLVED'"

        query += " ORDER BY cs.clash_id"

        cursor.execute(query, params)
        clashes = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return clashes

    def _generate_version_xml(self) -> str:
        """Generate bcf.version file content."""
        version = ET.Element('Version', VersionId=self.BCF_VERSION)
        ET.SubElement(version, 'DetailedVersion').text = '2.1'

        return self._xml_to_string(version)

    def _generate_project_xml(self) -> str:
        """Generate project.bcfp file content."""
        project = ET.Element('ProjectExtension')

        # Project metadata
        proj_elem = ET.SubElement(project, 'Project', ProjectId=str(uuid.uuid4()))
        ET.SubElement(proj_elem, 'Name').text = self.project_name

        # Extension schema (required by BCF 2.1)
        ext_schema = ET.SubElement(project, 'ExtensionSchema')

        return self._xml_to_string(project)

    def _generate_markup_xml(self, clash: Dict, topic_guid: str) -> str:
        """
        Generate markup.bcf for a single clash topic.

        BCF Markup structure:
        - Header (files, topic metadata)
        - Topic (title, status, priority, type, etc.)
        - Comments (discussion thread)
        - Viewpoints (3D camera references)
        """
        markup = ET.Element('Markup')

        # Header
        header = ET.SubElement(markup, 'Header')

        # Files referenced (IFC files)
        files = ET.SubElement(header, 'Files')
        # Note: We would add IFC file references here if we had the source file paths

        # Topic
        topic = ET.SubElement(markup, 'Topic',
            Guid=topic_guid,
            TopicType='Clash',
            TopicStatus=self._map_status_to_bcf(clash['status'])
        )

        # Reference links (element GUIDs)
        refs = ET.SubElement(topic, 'ReferenceLinks')
        ET.SubElement(refs, 'ReferenceLink').text = clash['guid_a']
        ET.SubElement(refs, 'ReferenceLink').text = clash['guid_b']

        # Title (descriptive clash name)
        title = f"Clash: {clash['name_a']} vs {clash['name_b']}"
        ET.SubElement(topic, 'Title').text = title

        # Priority (based on disciplines and severity)
        priority = self._calculate_priority(clash)
        ET.SubElement(topic, 'Priority').text = priority

        # Creation info
        ET.SubElement(topic, 'CreationDate').text = self._format_datetime(
            clash['date_created']
        )
        ET.SubElement(topic, 'CreationAuthor').text = self.author

        # Modified info
        if clash['date_modified']:
            ET.SubElement(topic, 'ModifiedDate').text = self._format_datetime(
                clash['date_modified']
            )

        # Assigned to
        if clash['assigned_to']:
            ET.SubElement(topic, 'AssignedTo').text = clash['assigned_to']

        # Description (detailed clash information)
        description = self._generate_clash_description(clash)
        ET.SubElement(topic, 'Description').text = description

        # Labels (disciplines, element types)
        labels = ET.SubElement(topic, 'Labels')
        ET.SubElement(labels, 'Label').text = clash['discipline_a']
        ET.SubElement(labels, 'Label').text = clash['discipline_b']
        ET.SubElement(labels, 'Label').text = clash['ifc_class_a']
        ET.SubElement(labels, 'Label').text = clash['ifc_class_b']

        # Comments (if any)
        if clash['comment']:
            comment = ET.SubElement(markup, 'Comment', Guid=str(uuid.uuid4()))
            ET.SubElement(comment, 'Date').text = self._format_datetime(
                clash['date_modified'] or clash['date_created']
            )
            ET.SubElement(comment, 'Author').text = self.author
            ET.SubElement(comment, 'Comment').text = clash['comment']

        # Viewpoints reference
        viewpoints_elem = ET.SubElement(markup, 'Viewpoints')
        vp = ET.SubElement(viewpoints_elem, 'ViewPoint', Guid=str(uuid.uuid4()))
        ET.SubElement(vp, 'Viewpoint').text = 'viewpoint.bcfv'
        ET.SubElement(vp, 'Snapshot').text = 'snapshot.png'

        return self._xml_to_string(markup)

    def _generate_viewpoint_xml(self, viewpoint_data: Dict) -> str:
        """
        Generate viewpoint.bcfv file content.

        Viewpoint contains 3D camera position, target, and up vector.

        Args:
            viewpoint_data: Dict with keys: camera, target, up (all tuples of 3 floats)
        """
        viewpoint = ET.Element('VisualizationInfo', Guid=str(uuid.uuid4()))

        # Components (elements to highlight)
        components = ET.SubElement(viewpoint, 'Components')

        # Camera perspective
        if 'camera' in viewpoint_data:
            camera_elem = ET.SubElement(viewpoint, 'PerspectiveCamera')

            # Camera position
            cam_pos = ET.SubElement(camera_elem, 'CameraViewPoint')
            ET.SubElement(cam_pos, 'X').text = str(viewpoint_data['camera'][0])
            ET.SubElement(cam_pos, 'Y').text = str(viewpoint_data['camera'][1])
            ET.SubElement(cam_pos, 'Z').text = str(viewpoint_data['camera'][2])

            # Camera direction (target - camera)
            if 'target' in viewpoint_data:
                cam = viewpoint_data['camera']
                tgt = viewpoint_data['target']
                direction = (tgt[0] - cam[0], tgt[1] - cam[1], tgt[2] - cam[2])

                cam_dir = ET.SubElement(camera_elem, 'CameraDirection')
                ET.SubElement(cam_dir, 'X').text = str(direction[0])
                ET.SubElement(cam_dir, 'Y').text = str(direction[1])
                ET.SubElement(cam_dir, 'Z').text = str(direction[2])

            # Camera up vector
            if 'up' in viewpoint_data:
                cam_up = ET.SubElement(camera_elem, 'CameraUpVector')
                ET.SubElement(cam_up, 'X').text = str(viewpoint_data['up'][0])
                ET.SubElement(cam_up, 'Y').text = str(viewpoint_data['up'][1])
                ET.SubElement(cam_up, 'Z').text = str(viewpoint_data['up'][2])

            # Field of view
            ET.SubElement(camera_elem, 'FieldOfView').text = '60.0'

        return self._xml_to_string(viewpoint)

    def _generate_clash_description(self, clash: Dict) -> str:
        """Generate detailed clash description for BCF topic."""
        lines = [
            f"Element A: {clash['name_a']} ({clash['ifc_class_a']})",
            f"Element B: {clash['name_b']} ({clash['ifc_class_b']})",
            f"Disciplines: {clash['discipline_a']} vs {clash['discipline_b']}",
        ]

        if clash['distance'] is not None:
            lines.append(f"Clearance: {clash['distance']:.3f}m")

        lines.append(f"Status: {clash['status']}")

        return "\n".join(lines)

    def _map_status_to_bcf(self, status: str) -> str:
        """
        Map internal clash status to BCF standard status.

        BCF standard statuses: Open, Resolved, Closed
        Our statuses: NEW, ACTIVE, REVIEWED, RESOLVED
        """
        mapping = {
            'NEW': 'Open',
            'ACTIVE': 'Open',
            'REVIEWED': 'Open',
            'RESOLVED': 'Resolved',
            'CLOSED': 'Closed'
        }
        return mapping.get(status, 'Open')

    def _calculate_priority(self, clash: Dict) -> str:
        """
        Calculate BCF priority based on clash characteristics.

        Priority levels: Critical, Major, Normal, Minor, Trivial

        Rules:
        - Structure vs Structure = Critical
        - MEP vs Structure = Major
        - MEP vs MEP = Normal
        - Others = Normal
        """
        disc_a = clash['discipline_a']
        disc_b = clash['discipline_b']

        # Structure vs Structure
        if disc_a == 'STR' and disc_b == 'STR':
            return 'Critical'

        # MEP vs Structure
        if ('STR' in [disc_a, disc_b] and
            any(x in [disc_a, disc_b] for x in ['HVAC', 'ELEC', 'PP', 'FP'])):
            return 'Major'

        # Default
        return 'Normal'

    def _format_datetime(self, dt_string: str) -> str:
        """
        Format datetime to BCF ISO 8601 format.

        BCF requires: YYYY-MM-DDTHH:MM:SS
        """
        try:
            # Parse various datetime formats
            if 'T' in dt_string:
                # Already in ISO format
                return dt_string.split('.')[0]  # Remove microseconds
            else:
                # Assume SQL datetime format
                dt = datetime.strptime(dt_string, '%Y-%m-%d %H:%M:%S')
                return dt.strftime('%Y-%m-%dT%H:%M:%S')
        except:
            # Fallback to current time
            return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    def _xml_to_string(self, element: ET.Element) -> str:
        """Convert XML element to formatted string with declaration."""
        xml_string = ET.tostring(element, encoding='unicode', method='xml')
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_string}'
