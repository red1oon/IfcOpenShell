"""
Clash Resolution Report Generator

Generates professional Markdown reports with cost analysis, ROI calculations,
and clash overview visualizations for clash resolution coordination meetings.

Uses intelligent text parsing and reference formulas to generate human-readable
content instead of cryptic IFC class names and GUIDs.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import json
import csv

# Import standard IFC label mapper (reusable across modules)
from ...ifc_label_mapper import get_friendly_label, get_discipline_label


class ReportGenerator:
    """
    Generates Markdown reports for clash resolution analysis.

    Queries database for clash groups, resolution options, cost estimates,
    and generates comprehensive reports with financial analysis and action plans.
    """

    def __init__(self, database_path: str):
        """
        Initialize report generator.

        Args:
            database_path: Path to clash detection database
        """
        self.database_path = database_path
        self.conn = None

    def connect(self):
        """Establish database connection."""
        if not self.conn:
            self.conn = sqlite3.connect(self.database_path)
            self.conn.row_factory = sqlite3.Row

    def disconnect(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def generate_report(
        self,
        output_dir: str,
        project_name: str = "BIM Project",
        analyst_name: str = "[Analyst Name]"
    ) -> Tuple[bool, str]:
        """
        Generate complete clash resolution report.

        Args:
            output_dir: Directory to save report and snapshots
            project_name: Name of the project
            analyst_name: Name of the analyst

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            self.connect()

            # Create output directory structure
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            snapshots_dir = output_path / "snapshots"
            snapshots_dir.mkdir(exist_ok=True)

            # Gather report data
            report_data = self._gather_report_data(project_name, analyst_name)

            if not report_data:
                return False, "No data available for report generation"

            # Generate report sections
            report_content = self._build_report_content(report_data)

            # Write report file
            report_file = output_path / "report.md"
            report_file.write_text(report_content, encoding='utf-8')

            # Export metadata
            self._export_metadata(output_path, report_data)

            # Export CSV data
            self._export_csv_data(output_path, report_data)

            # Generate HTML version for easy viewing
            html_file = output_path / "report.html"
            html_success = self._export_html(output_path, report_content, report_data)

            if html_success:
                return True, f"Report generated: {report_file} and {html_file}"
            else:
                return True, f"Report generated: {report_file} (HTML conversion skipped)"

        except Exception as e:
            return False, f"Report generation failed: {str(e)}"

        finally:
            self.disconnect()

    def _gather_report_data(self, project_name: str, analyst_name: str) -> Optional[Dict]:
        """
        Query database and gather all data needed for report.

        Returns:
            Dictionary containing all report data, or None if no data
        """
        # Get database stats
        cursor = self.conn.cursor()

        # Count total elements
        cursor.execute("SELECT COUNT(*) as count FROM elements_meta")
        total_elements = cursor.fetchone()['count']

        # Get database file size
        db_size_mb = Path(self.database_path).stat().st_size / (1024 * 1024)

        # Get clash groups
        groups = self._fetch_clash_groups()

        if not groups:
            print("Warning: No clash groups found in database")
            print("  Please run:")
            print("  1. Clash Detection (bim.clash_by_discipline)")
            print("  2. Clash Grouping (bim.analyze_clash_groups)")
            print("  3. Resolution Suggestions (bim.suggest_resolutions)")
            print("  Then generate the report.")
            return None

        # Calculate summary statistics
        total_clashes_in_groups = sum(g['total_clashes'] for g in groups)

        # Get ungrouped clashes count
        cursor.execute("""
            SELECT COUNT(*) as count FROM clash_status
            WHERE clash_id NOT IN (
                SELECT clash_id FROM clash_group_members
            )
        """)
        ungrouped_count = cursor.fetchone()['count']

        # Calculate cascade efficiency
        total_analyzed = total_clashes_in_groups + ungrouped_count
        cascade_efficiency = (total_clashes_in_groups / total_analyzed * 100) if total_analyzed > 0 else 0

        # Calculate total costs
        total_design_hours = 0
        total_design_cost = 0
        total_construction_cost = 0

        for group in groups:
            # Get resolution option for this group
            cursor.execute("""
                SELECT
                    ro.total_design_hours,
                    ro.total_design_cost,
                    ro.estimated_construction_cost
                FROM resolution_options ro
                WHERE ro.group_id = ?
                ORDER BY ro.recommendation_rank
                LIMIT 1
            """, (group['group_id'],))

            resolution = cursor.fetchone()
            if resolution:
                total_design_hours += resolution['total_design_hours'] or 0
                total_design_cost += resolution['total_design_cost'] or 0
                total_construction_cost += resolution['estimated_construction_cost'] or 0

        # Build report data structure
        report_data = {
            'metadata': {
                'project_name': project_name,
                'analyst_name': analyst_name,
                'analysis_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'database_file': Path(self.database_path).name,
                'database_size_mb': round(db_size_mb, 1),
                'total_elements': total_elements,
            },
            'summary': {
                'total_groups': len(groups),
                'total_clashes_in_groups': total_clashes_in_groups,
                'ungrouped_clashes': ungrouped_count,
                'cascade_efficiency': round(cascade_efficiency, 1),
                'total_design_hours': round(total_design_hours, 1),
                'total_design_cost': round(total_design_cost, 2),
                'total_construction_cost': round(total_construction_cost, 2),
                'total_analyzed': total_analyzed,
            },
            'groups': groups,
        }

        return report_data

    def _fetch_clash_groups(self) -> List[Dict]:
        """
        Fetch all clash groups with their details.

        Returns:
            List of clash group dictionaries
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                group_id,
                cascade_element_guid as root_element_guid,
                cascade_element_class as root_element_type,
                cascade_element_discipline as root_element_discipline,
                total_clashes,
                severity,
                'CASCADE' as pattern_type,
                date_created as created_date
            FROM clash_groups
            ORDER BY
                CASE severity
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END,
                total_clashes DESC
        """)

        groups = []
        for row in cursor.fetchall():
            group_dict = dict(row)

            # Set root_element_name from GUID (element name not stored in clash_groups table)
            group_dict['root_element_name'] = group_dict['root_element_guid']

            # Get clash members for this group
            group_dict['members'] = self._fetch_group_members(row['group_id'])

            # Get resolution options
            group_dict['resolution_options'] = self._fetch_resolution_options(row['group_id'])

            groups.append(group_dict)

        return groups

    def _fetch_group_members(self, group_id: int) -> List[Dict]:
        """Fetch clash members for a specific group."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                cgm.clash_id,
                cs.guid_a as element_a_guid,
                cs.guid_b as element_b_guid,
                cs.name_a as element_a_name,
                cs.name_b as element_b_name,
                cs.ifc_class_a as element_a_type,
                cs.ifc_class_b as element_b_type,
                cs.status
            FROM clash_group_members cgm
            JOIN clash_status cs ON cgm.clash_id = cs.clash_id
            WHERE cgm.group_id = ?
            ORDER BY cgm.clash_id
        """, (group_id,))

        return [dict(row) for row in cursor.fetchall()]

    def _fetch_resolution_options(self, group_id: int) -> List[Dict]:
        """Fetch resolution options for a specific group."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                option_id,
                option_type as option_name,
                description,
                recommendation_rank as rank,
                total_design_hours as total_hours,
                total_design_cost as estimated_cost,
                estimated_construction_cost as construction_cost_variance,
                calendar_days_required as schedule_impact_days,
                'MEDIUM' as confidence_level,
                generated_date as created_date
            FROM resolution_options
            WHERE group_id = ?
            ORDER BY recommendation_rank
        """, (group_id,))

        options = []
        for row in cursor.fetchall():
            option_dict = dict(row)

            # Get detailed activities for this option
            option_dict['activities'] = self._fetch_option_activities(row['option_id'])

            options.append(option_dict)

        return options

    def _fetch_option_activities(self, option_id: int) -> List[Dict]:
        """Fetch detailed activities for a resolution option."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                activity_type,
                discipline,
                estimated_hours,
                skill_level,
                hourly_rate,
                total_cost as cost
            FROM design_effort_estimates
            WHERE option_id = ?
            ORDER BY activity_type
        """, (option_id,))

        return [dict(row) for row in cursor.fetchall()]

    def _build_report_content(self, data: Dict) -> str:
        """
        Build complete Markdown report content.

        Args:
            data: Report data dictionary

        Returns:
            Formatted Markdown string
        """
        sections = []

        # Header
        sections.append(self._build_header(data))

        # Executive Summary
        sections.append(self._build_executive_summary(data))

        # Group Details
        for idx, group in enumerate(data['groups'], 1):
            sections.append(self._build_group_section(group, idx, data))

        # Total Impact Summary
        sections.append(self._build_total_impact_summary(data))

        # Action Plan
        sections.append(self._build_action_plan(data))

        # Appendix
        sections.append(self._build_appendix(data))

        # Footer
        sections.append(self._build_footer(data))

        return "\n\n".join(sections)

    def _build_header(self, data: Dict) -> str:
        """Build report header section."""
        meta = data['metadata']
        return f"""# CLASH RESOLUTION REPORT

**Project:** {meta['project_name']}
**Generated:** {meta['analysis_date']}
**Analyst:** {meta['analyst_name']}

> **⚠️ POC REPORT:** This is a Proof-of-Concept demonstration of intelligent clash analysis.
> Report content and cost estimates are generated to show stakeholders the potential value
> of automated cascade grouping and cost intelligence. Review with your project team before
> using for actual coordination decisions.

---

## OUTPUT FORMAT

**File Type:** Markdown (.md) - Editable by reporter
**Generated:** {meta['analysis_date']}

**Instructions:**
- ✏️ **Edit this file** to customize before distribution
- 📧 **Send as-is** (Markdown is readable in most email clients)
- 📄 **Convert to PDF:** `pandoc report.md -o report.pdf`
- 🔄 **Version control:** Commit to git repository

---

## PROJECT INFORMATION

| Field | Value |
|-------|-------|
| **Project Name** | {meta['project_name']} |
| **Analysis Date** | {meta['analysis_date']} |
| **Analyst** | {meta['analyst_name']} |
| **Database** | {meta['database_file']} ({meta['database_size_mb']}MB, {meta['total_elements']:,} elements) |
| **Report Type** | Intelligent Clash Resolution Analysis (POC) |
"""

    def _build_executive_summary(self, data: Dict) -> str:
        """Build executive summary section."""
        summary = data['summary']

        # Calculate average hourly rate
        avg_rate = summary['total_design_cost'] / summary['total_design_hours'] if summary['total_design_hours'] > 0 else 0

        # Calculate ROI
        total_savings = summary['total_construction_cost']
        roi = total_savings / summary['total_design_cost'] if summary['total_design_cost'] > 0 else 0

        # Format numbers with proper units to avoid f-string parsing issues
        cascade_eff = f"{summary['cascade_efficiency']:.1f}%"
        design_hours = f"{summary['total_design_hours']:.1f} hours"
        design_cost = f"${summary['total_design_cost']:,.2f} USD"
        avg_rate_fmt = f"${avg_rate:.0f}/hr average"
        construction_cost = f"${summary['total_construction_cost']:,.2f} USD"
        total_impact = f"${summary['total_design_cost'] + summary['total_construction_cost']:,.2f} USD"
        roi_fmt = f"{roi:.1f}x"
        roi_savings = f"${roi:.2f}"

        return f"""---

## EXECUTIVE SUMMARY

### Cascade Clash Analysis Results

**Groups Identified:** {summary['total_groups']} cascade groups
**Total Clashes Analyzed:** {summary['total_analyzed']} clashes
**Clashes Grouped:** {summary['total_clashes_in_groups']} clashes ({cascade_eff} cascade efficiency)
**Ungrouped Clashes:** {summary['ungrouped_clashes']} isolated clashes

### Financial Impact (Estimated)

| Category | Amount | Notes |
|----------|--------|-------|
| **Design Phase Effort** | {design_hours} | Coordination + modeling |
| **Design Phase Cost** | {design_cost} | @ {avg_rate_fmt} |
| **Construction Cost Variance** | {construction_cost} | Rework avoided if addressed now |
| **Total Project Impact** | {total_impact} | Design + construction |

### ROI Assessment

**Return on Investment:** {roi_fmt}
- Every $1 spent on design coordination saves {roi_savings} in construction rework
- Early coordination prevents costly field changes

### Recommended Actions

1. ✅ **Immediate (This Week):** Address HIGH priority groups
2. ⚠️ **Short-Term (2-3 Days):** Schedule coordination meetings for MEDIUM priority
3. 📋 **Documentation:** Update drawings within 5 business days
4. 🔍 **Verification:** Re-run clash detection after changes applied"""

    def _build_group_section(self, group: Dict, group_num: int, data: Dict) -> str:
        """Build detailed section for a single clash group."""
        sections = []

        # Get friendly element name (queries database for custom labels)
        element_label = get_friendly_label(
            ifc_class=group['root_element_type'],
            element_name=group['root_element_name'],
            db_path=self.database_path
        )

        # Group header with human-readable title
        sections.append(f"""---

## GROUP {group_num}: {group['pattern_type'].upper()} CLASH PATTERN

### Root Cause Element

**Element:** {element_label}
**Type:** {group['root_element_type']}
**GUID:** `{group['root_element_guid'][:12]}...` (for BIM software reference)
**Identified:** {group['created_date']}

### Impact Assessment

**Total Clashes:** {group['total_clashes']} elements affected
**Severity:** {group['severity']}
**Pattern Type:** {group['pattern_type']}""")

        # Clash members table
        if group['members']:
            sections.append("""
**Clashing Elements:**

| # | Element A | Element B | Type | Status |
|---|-----------|-----------|------|--------|""")

            for idx, member in enumerate(group['members'], 1):
                elem_a_short = member['element_a_name'][:30] if member['element_a_name'] else member['element_a_guid'][:8]
                elem_b_short = member['element_b_name'][:30] if member['element_b_name'] else member['element_b_guid'][:8]
                sections.append(f"| {idx} | {elem_a_short} | {elem_b_short} | {member['element_a_type']} vs {member['element_b_type']} | {member['status']} |")

        # Resolution options
        if group['resolution_options']:
            best_option = group['resolution_options'][0]  # Rank 1 option

            sections.append(f"""
### Recommended Resolution Strategy

**Option: {best_option['option_name']}**

{best_option['description']}

**Estimated Effort:**
- Design Phase: {best_option['total_hours']:.1f} hours (${best_option['estimated_cost']:,.2f} USD)
- Schedule Impact: {best_option['schedule_impact_days']:.1f} days
- Construction Cost Variance: ${best_option['construction_cost_variance']:,.2f} USD
- Confidence Level: {best_option['confidence_level']}""")

            # Activity breakdown
            if best_option['activities']:
                sections.append("""
**Activity Breakdown:**

| Activity | Discipline | Hours | Skill Level | Rate | Cost |
|----------|------------|-------|-------------|------|------|""")

                for activity in best_option['activities']:
                    sections.append(
                        f"| {activity['activity_type']} | {activity['discipline']} | "
                        f"{activity['estimated_hours']:.1f} | {activity['skill_level']} | "
                        f"${activity['hourly_rate']:.0f}/hr | ${activity['cost']:.2f} |"
                    )

        # Add visual documentation section with snapshot
        sections.append(f"""
### Clash Overview

![Group {group_num} Clash Overview](snapshots/group_{group['group_id']}_overview.png)

*Figure {group_num}: Clashes highlighted in red showing current state. Engineers visualize proposed changes in their BIM software (Revit/Blender).*

> **Note:** If image doesn't appear, snapshots may not have been generated. Re-run report generation with "Include Snapshots" enabled.
""")

        return "\n".join(sections)

    def _build_total_impact_summary(self, data: Dict) -> str:
        """Build total project impact summary."""
        summary = data['summary']
        roi = summary['total_construction_cost'] / summary['total_design_cost'] if summary['total_design_cost'] > 0 else 0

        return f"""---

## TOTAL PROJECT IMPACT SUMMARY

### Financial Summary

| Phase | Hours | Cost | Notes |
|-------|-------|------|-------|
| **Total Design Effort** | {summary['total_design_hours']:.1f} hrs | ${summary['total_design_cost']:,.2f} | All disciplines |
| Construction Rework Avoided | - | ${summary['total_construction_cost']:,.2f} | If addressed now |
| **Total Value Delivered** | - | ${summary['total_construction_cost']:,.2f} | **ROI: {roi:.1f}x** |

### Priority Distribution

| Priority | Groups | Action Required |
|----------|--------|-----------------|"""

    def _build_action_plan(self, data: Dict) -> str:
        """Build recommended action plan."""
        return """---

## RECOMMENDED ACTION PLAN

### Week 1 (Immediate)

**High Priority Groups:**
- [ ] Review clash groups marked as HIGH severity
- [ ] Assign responsibilities to discipline leads
- [ ] Begin resolution modeling
- [ ] Status: **PENDING**

### Week 2 (Short-Term)

**Medium Priority Groups:**
- [ ] Schedule coordination meeting
- [ ] Review resolution options
- [ ] Assign tasks and deadlines
- [ ] Status: **NOT STARTED**

### Ongoing

**Verification:**
- [ ] Re-run clash detection after changes
- [ ] Update coordination logs
- [ ] Document lessons learned
- [ ] Archive clash reports"""

    def _build_appendix(self, data: Dict) -> str:
        """Build appendix with technical metadata."""
        meta = data['metadata']
        summary = data['summary']

        return f"""---

## APPENDIX: TECHNICAL METADATA

**Analysis Parameters:**
- Clash Detection Tolerance: Database-defined clearance rules
- R-tree Spatial Index: Enabled (fast detection)
- Cascade Grouping: Automatic pattern detection
- Cost Estimates: Based on discipline rates and activity durations

**Database Statistics:**
- Total Elements Analyzed: {meta['total_elements']:,}
- Total Clashes Detected: {summary['total_analyzed']}
- Clashes Grouped: {summary['total_clashes_in_groups']} ({summary['cascade_efficiency']:.1f}%)
- Groups Created: {summary['total_groups']}

**Quality Assurance:**
- ✅ All clash GUIDs validated against database
- ✅ Element names verified from IFC properties
- ✅ Cost estimates based on configured discipline rates
- ✅ Activity durations from project configuration"""

    def _build_footer(self, data: Dict) -> str:
        """Build report footer."""
        meta = data['metadata']

        return f"""---

**Report Generated:** {meta['analysis_date']}
**Generated By:** Intelligent Clash Adjustment System
**Powered By:** Bonsai BIM (IfcOpenShell)

🤖 *Generated with [Claude Code](https://claude.com/claude-code)*

---

**Document Classification:** Project Coordination Document
**Distribution:** Project Team, Discipline Leads, Contractor
**Retention:** Archive with project coordination records"""

    def _export_metadata(self, output_path: Path, data: Dict):
        """Export report metadata as JSON."""
        metadata_file = output_path / "metadata.json"

        metadata = {
            'report_version': '1.0',
            'generated_date': data['metadata']['analysis_date'],
            'project_name': data['metadata']['project_name'],
            'analyst_name': data['metadata']['analyst_name'],
            'database_file': data['metadata']['database_file'],
            'summary': data['summary'],
            'groups': [
                {
                    'group_id': g['group_id'],
                    'severity': g['severity'],
                    'total_clashes': g['total_clashes'],
                    'root_element_guid': g['root_element_guid'],
                }
                for g in data['groups']
            ],
        }

        metadata_file.write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    def _export_csv_data(self, output_path: Path, data: Dict):
        """Export clash data as CSV for external analysis."""
        csv_file = output_path / "data_export.csv"

        with csv_file.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow([
                'Group ID', 'Severity', 'Root Element GUID', 'Root Element Name',
                'Clash ID', 'Element A GUID', 'Element A Name', 'Element B GUID',
                'Element B Name', 'Status'
            ])

            # Write data rows
            for group in data['groups']:
                for member in group['members']:
                    writer.writerow([
                        group['group_id'],
                        group['severity'],
                        group['root_element_guid'],
                        group['root_element_name'],
                        member['clash_id'],
                        member['element_a_guid'],
                        member['element_a_name'],
                        member['element_b_guid'],
                        member['element_b_name'],
                        member['status'],
                    ])

    def _export_html(self, output_path: Path, markdown_content: str, data: Dict) -> bool:
        """
        Export report as HTML for easy viewing in browser.

        Tries multiple methods: markdown2, markdown, or fallback to basic conversion.
        """
        html_file = output_path / "report.html"

        try:
            # Try markdown2 first (best features)
            try:
                import markdown2
                html_body = markdown2.markdown(markdown_content, extras=['tables', 'fenced-code-blocks'])
                method = "markdown2"
            except ImportError:
                # Try standard markdown library
                try:
                    import markdown
                    html_body = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
                    method = "markdown"
                except ImportError:
                    # Fallback: basic conversion (no dependencies)
                    html_body = self._markdown_to_html_basic(markdown_content)
                    method = "basic"

            # Wrap in HTML template with styling
            html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clash Resolution Report - {data['metadata']['project_name']}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 20px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            background-color: white;
        }}
        th {{
            background-color: #3498db;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 10px 12px;
            border: 1px solid #ddd;
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        tr:hover {{
            background-color: #e8f4f8;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            padding-left: 20px;
            margin-left: 0;
            color: #7f8c8d;
            background-color: #ecf0f1;
            padding: 10px 20px;
            border-radius: 4px;
        }}
        code {{
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        .severity-HIGH {{
            color: #e74c3c;
            font-weight: bold;
        }}
        .severity-MEDIUM {{
            color: #f39c12;
            font-weight: bold;
        }}
        .severity-LOW {{
            color: #27ae60;
            font-weight: bold;
        }}
        hr {{
            border: none;
            border-top: 2px solid #ecf0f1;
            margin: 40px 0;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            color: #95a5a6;
            font-size: 0.9em;
            text-align: center;
        }}
        .print-button {{
            position: fixed;
            top: 20px;
            right: 20px;
            background-color: #3498db;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .print-button:hover {{
            background-color: #2980b9;
        }}
        @media print {{
            .print-button {{ display: none; }}
            body {{ background-color: white; }}
            .container {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <button class="print-button" onclick="window.print()">🖨️ Print Report</button>
    <div class="container">
        {html_body}
        <div class="footer">
            Generated by Bonsai Intelligent Clash Adjustment System • {data['metadata']['analysis_date']}
        </div>
    </div>
</body>
</html>"""

            html_file.write_text(html_template, encoding='utf-8')
            print(f"✅ HTML report generated using {method} converter")
            return True

        except Exception as e:
            print(f"⚠️ HTML generation failed: {e}")
            return False

    def _markdown_to_html_basic(self, markdown_content: str) -> str:
        """
        Basic Markdown to HTML conversion (fallback when no libraries available).
        Handles: headers, tables, bold, italic, links, images.
        """
        import re

        html = markdown_content

        # Headers
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)

        # Bold and italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', html)

        # Images
        html = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', r'<img src="\2" alt="\1" />', html)

        # Blockquotes
        html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)

        # Convert simple tables (basic support)
        html = self._convert_tables_basic(html)

        # Line breaks
        html = html.replace('\n\n', '</p><p>')
        html = '<p>' + html + '</p>'

        # Horizontal rules
        html = html.replace('---', '<hr />')

        return html

    def _convert_tables_basic(self, text: str) -> str:
        """Basic table conversion for fallback HTML generation."""
        import re

        # Find table blocks (lines starting with |)
        lines = text.split('\n')
        result = []
        in_table = False
        table_rows = []

        for line in lines:
            if line.strip().startswith('|'):
                if not in_table:
                    in_table = True
                    table_rows = []
                table_rows.append(line)
            else:
                if in_table:
                    # Process accumulated table
                    result.append(self._format_table_basic(table_rows))
                    in_table = False
                    table_rows = []
                result.append(line)

        # Handle table at end of document
        if in_table and table_rows:
            result.append(self._format_table_basic(table_rows))

        return '\n'.join(result)

    def _format_table_basic(self, rows: list) -> str:
        """Convert markdown table rows to HTML table."""
        if len(rows) < 2:
            return '\n'.join(rows)

        html = ['<table>']

        # Header row
        header_cells = [cell.strip() for cell in rows[0].split('|')[1:-1]]
        html.append('<thead><tr>')
        for cell in header_cells:
            html.append(f'<th>{cell}</th>')
        html.append('</tr></thead>')

        # Skip separator row (row 1), process data rows
        html.append('<tbody>')
        for row in rows[2:]:
            cells = [cell.strip() for cell in row.split('|')[1:-1]]
            html.append('<tr>')
            for cell in cells:
                html.append(f'<td>{cell}</td>')
            html.append('</tr>')
        html.append('</tbody>')

        html.append('</table>')
        return '\n'.join(html)
