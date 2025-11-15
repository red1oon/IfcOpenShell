"""
Intelligent Clash Adjustment Engine (POC)
==========================================

Generates resolution options with design effort and cost estimates.

Key Principle: Optimize DESIGN EFFORT (not construction cost) during coordination.

POC Scope (Phase 1):
- Single resolution type: MEP duct reroute
- Basic design effort estimation
- Simple ranking by total design cost
- Manual effort estimates (learning system for Phase 2)

Part of: Intelligent Clash Adjustment POC
"""

import sqlite3
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class DesignEffortEstimate:
    """Represents design effort for a specific discipline/activity"""
    discipline: str
    activity_type: str
    estimated_hours: float
    skill_level: str
    hourly_rate: float
    calendar_days: float
    confidence: str = 'medium'
    requires_approval: bool = False
    approval_days: float = 0.0


@dataclass
class ResolutionOption:
    """Represents a single resolution alternative"""
    option_id: str
    option_type: str
    description: str
    rank: int

    # Design effort (primary optimization)
    total_design_hours: float
    total_design_cost: float

    # Schedule impact (secondary)
    calendar_days: float
    schedule_delay_cost: float

    # Construction cost (constraint)
    construction_cost: float
    exceeds_budget: bool

    # Technical
    technically_feasible: bool
    feasibility_notes: str

    # Risk
    risk_score: int
    risk_category: str
    risk_factors: List[str]

    # Impact
    affected_disciplines: List[str]
    clashes_resolved: int

    # Detailed breakdown
    effort_estimates: List[DesignEffortEstimate]


class ResolutionAnalysisEngine:
    """
    Generates and ranks resolution options for clashes/groups.

    POC Implementation: Focus on single resolution type (duct reroute)
    with basic design effort estimation.
    """

    # Project-level constants (should be configurable)
    PROJECT_DAILY_BURN_RATE = 3000.0  # $/day (owner carrying + general conditions + design team)
    COORDINATION_BUDGET_ALLOWANCE = 50000.0  # $ available for coordination changes

    # Activity duration defaults (hours per activity type)
    ACTIVITY_DURATIONS = {
        'mep_duct_reroute_modeling': 4.0,  # Model duct reroute in BIM
        'mep_clearance_verification': 1.0,  # Verify no new clashes
        'mep_documentation_update': 2.0,    # Update MEP drawings
        'coordination_meeting': 0.5,        # Discuss change in coordination meeting
    }

    def __init__(self, db_path: str):
        """
        Initialize resolution engine.

        Args:
            db_path: Path to clash_status.db (with resolution tables)
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def generate_options_for_group(self, group_id: str) -> List[ResolutionOption]:
        """
        Generate resolution options for a clash group.

        Now generates 2-4 options per group:
        - Option 1: Modify cascade element (always)
        - Option 2: Modify clashing elements (if viable)
        - Option 3: Coordination solution - penetrations/clearances (if viable)
        - Option 4: Accept clash with justification (if minimal severity)

        Args:
            group_id: Clash group ID

        Returns:
            List of ResolutionOption objects, ranked by total design cost
        """
        # Get group details
        self.cursor.execute("""
            SELECT
                cascade_element_guid,
                cascade_element_class,
                cascade_element_discipline,
                total_clashes,
                affected_classes,
                affected_disciplines,
                severity
            FROM clash_groups
            WHERE group_id = ?
        """, (group_id,))

        group_data = self.cursor.fetchone()
        if not group_data:
            return []

        cascade_guid, cascade_class, cascade_disc, total_clashes, affected_classes_json, affected_disciplines_json, severity = group_data
        affected_classes = json.loads(affected_classes_json)
        affected_disciplines = json.loads(affected_disciplines_json)

        options = []

        # Option 1: Always try to modify cascade element (primary strategy)
        option1 = self._generate_modify_cascade_option(
            group_id, cascade_class, cascade_disc, total_clashes, affected_classes, affected_disciplines, severity
        )
        if option1:
            options.append(option1)

        # Option 2: Modify clashing elements instead (alternative strategy)
        # Viable when: cascade element is structural/architectural (harder to move)
        is_cascade_hard_to_move = (
            cascade_disc in ['STR', 'ARC'] and
            any(keyword in cascade_class for keyword in ['Slab', 'Beam', 'Column', 'Wall'])
        )
        has_movable_clashing_elements = any(
            cls for cls in affected_classes
            if any(keyword in cls for keyword in ['Duct', 'Pipe', 'Cable', 'Conduit'])
        )

        if is_cascade_hard_to_move and has_movable_clashing_elements:
            option2 = self._generate_modify_clashing_option(
                group_id, cascade_class, cascade_disc, total_clashes, affected_classes, affected_disciplines, severity
            )
            if option2:
                options.append(option2)

        # Option 3: Coordination solution (penetrations, clearances)
        # Viable when: Small clash count, architectural openings, or minor clearance issues
        is_coordination_viable = (
            'Opening' in cascade_class or
            (total_clashes <= 5 and severity in ['LOW', 'MEDIUM'])
        )

        if is_coordination_viable:
            option3 = self._generate_coordination_option(
                group_id, cascade_class, cascade_disc, total_clashes, affected_classes, affected_disciplines, severity
            )
            if option3:
                options.append(option3)

        # Option 4: Accept clash (document as acceptable)
        # Viable when: Very small clearance issue, modeling tolerance, or minor severity
        is_acceptable_scenario = (
            total_clashes <= 4 and
            severity in ['LOW', 'MEDIUM'] and
            'Opening' not in cascade_class  # Don't accept opening clashes
        )

        if is_acceptable_scenario:
            option4 = self._generate_accept_option(
                group_id, cascade_class, cascade_disc, total_clashes, affected_classes, affected_disciplines, severity
            )
            if option4:
                options.append(option4)

        # Rank options by design cost (lower = better)
        for i, opt in enumerate(sorted(options, key=lambda o: o.total_design_cost), 1):
            opt.rank = i

        return options

    def _generate_modify_cascade_option(self, group_id: str, element_class: str,
                                        discipline: str, total_clashes: int,
                                        affected_classes: List[str],
                                        affected_disciplines: List[str],
                                        severity: str) -> Optional[ResolutionOption]:
        """
        Generate Option 1: Modify the cascade element to resolve clashes.

        Design Effort Activities:
        1. Modeling: Adjust element in BIM
        2. Verification: Check clearances to other elements
        3. Documentation: Update coordination drawings
        4. Coordination: Present change in coordination meeting

        Args:
            group_id: Clash group ID
            element_class: IFC class of cascade element
            discipline: Discipline of cascade element
            total_clashes: Number of clashes in group
            affected_classes: Classes of affected elements
            affected_disciplines: Disciplines affected
            severity: Group severity level

        Returns:
            ResolutionOption or None if not applicable
        """
        # POC: Generate option for any element type
        # Determine what type of resolution this is
        if any(keyword in element_class for keyword in ['Duct', 'Pipe', 'Cable', 'Conduit']):
            resolution_type = 'reroute_mep'
            action_verb = 'Reroute'
        elif 'Slab' in element_class:
            resolution_type = 'adjust_slab'
            action_verb = 'Adjust'
        elif 'Proxy' in element_class:
            resolution_type = 'relocate_element'
            action_verb = 'Relocate'
        else:
            resolution_type = 'coordinate_element'
            action_verb = 'Coordinate'

        # Get discipline rates (use generic if discipline unknown)
        discipline_for_rate = discipline if discipline and discipline != 'Unknown' else 'ARCHITECTURE'

        self.cursor.execute("""
            SELECT hourly_rate FROM discipline_rates
            WHERE discipline = ? AND skill_level = 'intermediate'
            ORDER BY effective_date DESC LIMIT 1
        """, (discipline_for_rate,))

        rate_result = self.cursor.fetchone()
        base_rate = rate_result[0] if rate_result else 125.0  # Default fallback

        # Design effort estimates
        effort_estimates = []

        # Activity 1: Modeling (MEP engineer)
        modeling_hours = self.ACTIVITY_DURATIONS['mep_duct_reroute_modeling']
        # Complexity factor: More clashes = more complex reroute
        complexity_multiplier = 1.0 + (total_clashes - 3) * 0.1  # +10% per clash above 3
        modeling_hours *= complexity_multiplier

        effort_estimates.append(DesignEffortEstimate(
            discipline=discipline_for_rate,
            activity_type='modeling',
            estimated_hours=modeling_hours,
            skill_level='intermediate',
            hourly_rate=base_rate,
            calendar_days=1.0,  # Can complete in 1 day
            confidence='medium'
        ))

        # Activity 2: Clearance verification
        verification_hours = self.ACTIVITY_DURATIONS['mep_clearance_verification']
        effort_estimates.append(DesignEffortEstimate(
            discipline=discipline_for_rate,
            activity_type='verification',
            estimated_hours=verification_hours,
            skill_level='intermediate',
            hourly_rate=base_rate,
            calendar_days=0.5,
            confidence='high'
        ))

        # Activity 3: Documentation updates
        doc_hours = self.ACTIVITY_DURATIONS['mep_documentation_update']
        # More sheets if affecting multiple element types
        sheets_affected = min(len(set(affected_classes)), 4)  # Cap at 4 sheets
        doc_hours *= sheets_affected * 0.5 if sheets_affected > 0 else 1.0  # 50% of base time per sheet

        effort_estimates.append(DesignEffortEstimate(
            discipline=discipline_for_rate,
            activity_type='documentation',
            estimated_hours=doc_hours,
            skill_level='junior',
            hourly_rate=base_rate * 0.75,  # Junior rate
            calendar_days=1.0,
            confidence='medium'
        ))

        # Activity 4: Coordination meeting
        coord_hours = self.ACTIVITY_DURATIONS['coordination_meeting']
        effort_estimates.append(DesignEffortEstimate(
            discipline=discipline_for_rate,
            activity_type='coordination',
            estimated_hours=coord_hours,
            skill_level='intermediate',
            hourly_rate=base_rate,
            calendar_days=2.0,  # Wait for next coordination meeting
            confidence='high'
        ))

        # Calculate totals
        total_hours = sum(e.estimated_hours for e in effort_estimates)
        total_cost = sum(e.estimated_hours * e.hourly_rate for e in effort_estimates)
        calendar_days = max(e.calendar_days for e in effort_estimates)  # Critical path
        schedule_cost = calendar_days * self.PROJECT_DAILY_BURN_RATE

        # Construction cost estimate (parametric)
        # Rough estimate: $50/LF of duct + $300 per elbow
        # Assume 10 LF reroute + 2 elbows for typical clash group
        construction_cost = (10 * 50) + (2 * 300)  # $1,100
        exceeds_budget = construction_cost > (self.COORDINATION_BUDGET_ALLOWANCE * 0.1)  # >10% of allowance

        # Risk assessment
        risk_factors = []
        risk_score = 0

        if total_clashes >= 5:
            risk_factors.append('complex_reroute')
            risk_score += 15

        if 'Beam' in str(affected_classes):
            risk_factors.append('structural_coordination')
            risk_score += 10

        if sheets_affected >= 3:
            risk_factors.append('documentation_cascade')
            risk_score += 10

        # Base risk for any reroute
        risk_score += 15

        risk_category = self._categorize_risk(risk_score)

        # Generate option
        option_id = str(uuid.uuid4())

        affected_summary = ', '.join(affected_classes[:3]) if affected_classes else 'other elements'

        description = (
            f"{action_verb} {element_class.replace('Ifc', '')} to avoid conflicts. "
            f"Resolves {total_clashes} clashes with {affected_summary}."
        )

        return ResolutionOption(
            option_id=option_id,
            option_type=resolution_type,
            description=description,
            rank=1,  # Will be updated when ranking all options
            total_design_hours=total_hours,
            total_design_cost=total_cost,
            calendar_days=calendar_days,
            schedule_delay_cost=schedule_cost,
            construction_cost=construction_cost,
            exceeds_budget=exceeds_budget,
            technically_feasible=True,
            feasibility_notes='Standard MEP reroute, no structural implications',
            risk_score=risk_score,
            risk_category=risk_category,
            risk_factors=risk_factors,
            affected_disciplines=[discipline_for_rate],
            clashes_resolved=total_clashes,
            effort_estimates=effort_estimates
        )

    def _generate_modify_clashing_option(self, group_id: str, element_class: str,
                                         discipline: str, total_clashes: int,
                                         affected_classes: List[str],
                                         affected_disciplines: List[str],
                                         severity: str) -> Optional[ResolutionOption]:
        """
        Generate Option 2: Modify the clashing elements instead of cascade element.

        Viable when cascade element is hard to move (structural/architectural)
        but clashing elements are movable (MEP).

        Args: Same as _generate_modify_cascade_option
        Returns: ResolutionOption for modifying clashing elements
        """
        # Determine primary clashing element type
        mep_classes = [cls for cls in affected_classes if any(k in cls for k in ['Duct', 'Pipe', 'Cable', 'Conduit'])]
        if not mep_classes:
            return None

        primary_class = mep_classes[0]

        # Get discipline rate for affected MEP discipline
        mep_discipline = affected_disciplines[0] if affected_disciplines else 'MEP'

        self.cursor.execute("""
            SELECT hourly_rate FROM discipline_rates
            WHERE discipline = ? AND skill_level = 'intermediate'
            ORDER BY effective_date DESC LIMIT 1
        """, (mep_discipline,))

        rate_result = self.cursor.fetchone()
        base_rate = rate_result[0] if rate_result else 140.0  # MEP typically higher rate

        # Design effort - rerouting multiple clashing elements is harder
        effort_estimates = []

        # Modeling: Reroute each clashing element
        modeling_hours = 5.0 * min(total_clashes, 3)  # Cap scaling at 3 elements
        effort_estimates.append(DesignEffortEstimate(
            discipline=mep_discipline,
            activity_type='modeling',
            estimated_hours=modeling_hours,
            skill_level='intermediate',
            hourly_rate=base_rate,
            calendar_days=2.0,  # More complex
            confidence='medium'
        ))

        # Verification
        verification_hours = 1.5
        effort_estimates.append(DesignEffortEstimate(
            discipline=mep_discipline,
            activity_type='verification',
            estimated_hours=verification_hours,
            skill_level='intermediate',
            hourly_rate=base_rate,
            calendar_days=0.5,
            confidence='high'
        ))

        # Documentation
        doc_hours = 3.0
        effort_estimates.append(DesignEffortEstimate(
            discipline=mep_discipline,
            activity_type='documentation',
            estimated_hours=doc_hours,
            skill_level='junior',
            hourly_rate=base_rate * 0.75,
            calendar_days=1.0,
            confidence='medium'
        ))

        # Coordination
        coord_hours = 1.0  # More coordination needed
        effort_estimates.append(DesignEffortEstimate(
            discipline=mep_discipline,
            activity_type='coordination',
            estimated_hours=coord_hours,
            skill_level='senior',
            hourly_rate=base_rate * 1.2,
            calendar_days=2.0,
            confidence='high'
        ))

        total_hours = sum(e.estimated_hours for e in effort_estimates)
        total_cost = sum(e.estimated_hours * e.hourly_rate for e in effort_estimates)
        calendar_days = max(e.calendar_days for e in effort_estimates)
        schedule_cost = calendar_days * self.PROJECT_DAILY_BURN_RATE

        construction_cost = 800.0 * min(total_clashes, 3)  # Multiple reroutes
        exceeds_budget = construction_cost > (self.COORDINATION_BUDGET_ALLOWANCE * 0.15)

        # Risk
        risk_factors = ['multiple_elements', 'mep_coordination']
        risk_score = 30 + (total_clashes * 5)
        risk_category = self._categorize_risk(risk_score)

        option_id = str(uuid.uuid4())
        description = (
            f"Reroute {total_clashes} conflicting {primary_class.replace('Ifc', '')} elements "
            f"around existing {element_class.replace('Ifc', '')}. "
            f"Preserves {discipline} design intent."
        )

        return ResolutionOption(
            option_id=option_id,
            option_type='reroute_clashing_elements',
            description=description,
            rank=1,
            total_design_hours=total_hours,
            total_design_cost=total_cost,
            calendar_days=calendar_days,
            schedule_delay_cost=schedule_cost,
            construction_cost=construction_cost,
            exceeds_budget=exceeds_budget,
            technically_feasible=True,
            feasibility_notes=f'Alternative approach - modify {mep_discipline} instead of {discipline}',
            risk_score=risk_score,
            risk_category=risk_category,
            risk_factors=risk_factors,
            affected_disciplines=affected_disciplines,
            clashes_resolved=total_clashes,
            effort_estimates=effort_estimates
        )

    def _generate_coordination_option(self, group_id: str, element_class: str,
                                       discipline: str, total_clashes: int,
                                       affected_classes: List[str],
                                       affected_disciplines: List[str],
                                       severity: str) -> Optional[ResolutionOption]:
        """
        Generate Option 3: Coordination solution (penetrations, clearances).

        Viable for openings, small clash counts, or clearance verification.

        Args: Same as _generate_modify_cascade_option
        Returns: ResolutionOption for coordination approach
        """
        # Determine coordination strategy
        if 'Opening' in element_class:
            strategy = 'Verify penetration coordination'
            activity_desc = 'penetration_coordination'
        else:
            strategy = 'Document acceptable clearances'
            activity_desc = 'clearance_verification'

        # Lower effort than rerouting
        coordination_rate = 125.0

        effort_estimates = []

        # Review and verification (primary activity)
        review_hours = 2.0 + (total_clashes * 0.3)
        effort_estimates.append(DesignEffortEstimate(
            discipline='COORDINATION',
            activity_type=activity_desc,
            estimated_hours=review_hours,
            skill_level='intermediate',
            hourly_rate=coordination_rate,
            calendar_days=1.0,
            confidence='high'
        ))

        # Documentation
        doc_hours = 1.5
        effort_estimates.append(DesignEffortEstimate(
            discipline='COORDINATION',
            activity_type='documentation',
            estimated_hours=doc_hours,
            skill_level='intermediate',
            hourly_rate=coordination_rate,
            calendar_days=0.5,
            confidence='high'
        ))

        total_hours = sum(e.estimated_hours for e in effort_estimates)
        total_cost = sum(e.estimated_hours * e.hourly_rate for e in effort_estimates)
        calendar_days = max(e.calendar_days for e in effort_estimates)
        schedule_cost = calendar_days * self.PROJECT_DAILY_BURN_RATE

        # Minimal construction cost (coordination only)
        construction_cost = 100.0 * total_clashes  # Administrative/coordination cost
        exceeds_budget = False

        # Low risk
        risk_factors = ['coordination_dependency']
        risk_score = 10 + (total_clashes * 2)
        risk_category = self._categorize_risk(risk_score)

        option_id = str(uuid.uuid4())
        affected_summary = ', '.join(affected_classes[:2]) if affected_classes else 'other elements'

        description = (
            f"{strategy} for {element_class.replace('Ifc', '')} with {total_clashes} clashes. "
            f"Verify code compliance and document coordination with {affected_summary}."
        )

        return ResolutionOption(
            option_id=option_id,
            option_type='coordination_solution',
            description=description,
            rank=1,
            total_design_hours=total_hours,
            total_design_cost=total_cost,
            calendar_days=calendar_days,
            schedule_delay_cost=schedule_cost,
            construction_cost=construction_cost,
            exceeds_budget=exceeds_budget,
            technically_feasible=True,
            feasibility_notes='Lowest cost option - verify coordination is acceptable',
            risk_score=risk_score,
            risk_category=risk_category,
            risk_factors=risk_factors,
            affected_disciplines=affected_disciplines,
            clashes_resolved=total_clashes,
            effort_estimates=effort_estimates
        )

    def _generate_accept_option(self, group_id: str, element_class: str,
                                 discipline: str, total_clashes: int,
                                 affected_classes: List[str],
                                 affected_disciplines: List[str],
                                 severity: str) -> Optional[ResolutionOption]:
        """
        Generate Option 4: Accept clash with documented justification.

        Viable for minimal severity, modeling tolerance, or verified clearances.

        Args: Same as _generate_modify_cascade_option
        Returns: ResolutionOption for accepting clash
        """
        # Minimal effort - just documentation
        coordination_rate = 125.0

        effort_estimates = []

        # Review to justify acceptance
        review_hours = 0.5 + (total_clashes * 0.2)
        effort_estimates.append(DesignEffortEstimate(
            discipline='COORDINATION',
            activity_type='clash_review',
            estimated_hours=review_hours,
            skill_level='intermediate',
            hourly_rate=coordination_rate,
            calendar_days=0.5,
            confidence='high'
        ))

        # Document justification
        doc_hours = 1.0
        effort_estimates.append(DesignEffortEstimate(
            discipline='COORDINATION',
            activity_type='documentation',
            estimated_hours=doc_hours,
            skill_level='intermediate',
            hourly_rate=coordination_rate,
            calendar_days=0.5,
            confidence='high'
        ))

        total_hours = sum(e.estimated_hours for e in effort_estimates)
        total_cost = sum(e.estimated_hours * e.hourly_rate for e in effort_estimates)
        calendar_days = max(e.calendar_days for e in effort_estimates)
        schedule_cost = calendar_days * self.PROJECT_DAILY_BURN_RATE

        # Zero construction cost
        construction_cost = 0.0
        exceeds_budget = False

        # Very low risk (if justified properly)
        risk_factors = ['requires_justification', 'potential_field_issue']
        risk_score = 15 if severity == 'LOW' else 25
        risk_category = self._categorize_risk(risk_score)

        option_id = str(uuid.uuid4())
        affected_summary = ', '.join(affected_classes[:2]) if affected_classes else 'other elements'

        description = (
            f"Accept {total_clashes} clashes as within tolerance/clearance. "
            f"Document justification for {element_class.replace('Ifc', '')} conflicts with {affected_summary}. "
            f"Lowest cost option."
        )

        return ResolutionOption(
            option_id=option_id,
            option_type='accept_clash',
            description=description,
            rank=1,
            total_design_hours=total_hours,
            total_design_cost=total_cost,
            calendar_days=calendar_days,
            schedule_delay_cost=schedule_cost,
            construction_cost=construction_cost,
            exceeds_budget=exceeds_budget,
            technically_feasible=True,
            feasibility_notes='Minimal cost - requires justification and stakeholder approval',
            risk_score=risk_score,
            risk_category=risk_category,
            risk_factors=risk_factors,
            affected_disciplines=affected_disciplines,
            clashes_resolved=total_clashes,
            effort_estimates=effort_estimates
        )

    def _categorize_risk(self, score: int) -> str:
        """Categorize numeric risk score"""
        if score < 20:
            return 'LOW'
        elif score < 50:
            return 'MEDIUM'
        elif score < 80:
            return 'HIGH'
        else:
            return 'CRITICAL'

    def save_options_to_database(self, group_id: str, options: List[ResolutionOption]) -> None:
        """
        Save resolution options to database for persistence.

        Args:
            group_id: Clash group ID
            options: List of resolution options
        """
        # Delete existing options for this group to prevent duplicates
        # This handles re-generation scenarios where options are updated
        self.cursor.execute("""
            DELETE FROM design_effort_estimates
            WHERE option_id IN (
                SELECT option_id FROM resolution_options WHERE group_id = ?
            )
        """, (group_id,))

        self.cursor.execute("""
            DELETE FROM resolution_options WHERE group_id = ?
        """, (group_id,))

        now = datetime.now().isoformat()

        for option in options:
            # Insert resolution option
            self.cursor.execute("""
                INSERT INTO resolution_options (
                    option_id, clash_id, group_id,
                    option_type, description, recommendation_rank,
                    total_design_hours, total_design_cost,
                    calendar_days_required, schedule_delay_cost,
                    estimated_construction_cost, exceeds_budget,
                    technically_feasible, feasibility_notes,
                    risk_score, risk_category, risk_factors,
                    affected_disciplines, clashes_resolved,
                    generated_date, generated_by
                ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                option.option_id, group_id,
                option.option_type, option.description, option.rank,
                option.total_design_hours, option.total_design_cost,
                option.calendar_days, option.schedule_delay_cost,
                option.construction_cost, int(option.exceeds_budget),
                int(option.technically_feasible), option.feasibility_notes,
                option.risk_score, option.risk_category, json.dumps(option.risk_factors),
                json.dumps(option.affected_disciplines), option.clashes_resolved,
                now, 'resolution_engine_v1'
            ))

            # Insert design effort estimates
            for effort in option.effort_estimates:
                effort_id = str(uuid.uuid4())
                self.cursor.execute("""
                    INSERT INTO design_effort_estimates (
                        effort_id, option_id,
                        discipline, activity_type,
                        estimated_hours, skill_level, hourly_rate, total_cost,
                        calendar_days_required,
                        confidence_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    effort_id, option.option_id,
                    effort.discipline, effort.activity_type,
                    effort.estimated_hours, effort.skill_level, effort.hourly_rate,
                    effort.estimated_hours * effort.hourly_rate,
                    effort.calendar_days,
                    effort.confidence
                ))

        self.conn.commit()
        print(f"✓ Saved {len(options)} resolution options to database")

    def analyze_group(self, group_id: str) -> List[ResolutionOption]:
        """
        Complete analysis: Generate options and save to database.

        Args:
            group_id: Clash group ID

        Returns:
            List of resolution options, ranked by design cost
        """
        options = self.generate_options_for_group(group_id)

        if options:
            self.save_options_to_database(group_id, options)

        return options

    def enhance_options_with_proximity(
        self,
        options: List[ResolutionOption],
        cascade_position_mm: Tuple[float, float, float],
        check_radius_mm: float = 2000
    ) -> List[Dict]:
        """
        Enhance resolution options with proximity impact analysis

        Adds proximity data for:
        - Visualization (highlight impacted elements in red)
        - Report generation (list nearby elements, take snapshots)
        - Impact warnings (new potential clashes)

        Args:
            options: List of resolution options to enhance
            cascade_position_mm: Current position of cascade element (x,y,z) in mm
            check_radius_mm: Radius to check for nearby elements (default 2m)

        Returns:
            Enhanced options (as dicts) with proximity_impact field added
        """
        from .proximity_analyzer import ProximityAnalyzer

        analyzer = ProximityAnalyzer(self.db_path)

        enhanced_options = []
        for option in options:
            # Analyze proximity impact
            impact = analyzer.analyze_impact_radius(
                element_guid=option.option_id,  # Using option_id as temp GUID
                current_position_mm=cascade_position_mm,
                proposed_position_mm=cascade_position_mm,  # Same pos for now, analyze current state
                check_radius_mm=check_radius_mm
            )

            # Convert option to dict and add proximity data
            option_dict = option.__dict__.copy()
            option_dict['proximity_impact'] = {
                'nearby_elements_count': impact['nearby_count'],
                'potential_new_clashes': len(impact['potential_clashes']),
                'clearance_warnings': impact['clearance_warnings'],
                'impacted_elements': impact['potential_clashes'],  # For red visualization
            }

            enhanced_options.append(option_dict)

        return enhanced_options

    def close(self):
        """Close database connection"""
        self.conn.close()


def analyze_all_groups(db_path: str) -> Dict[str, List[ResolutionOption]]:
    """
    Analyze all clash groups and generate resolution options.

    Args:
        db_path: Path to clash_status.db

    Returns:
        Dict mapping group_id to list of resolution options
    """
    engine = ResolutionAnalysisEngine(db_path)

    # Get all groups
    engine.cursor.execute("SELECT group_id FROM clash_groups ORDER BY total_clashes DESC")
    group_ids = [row[0] for row in engine.cursor.fetchall()]

    if not group_ids:
        print("No clash groups found. Run clash grouping first.")
        engine.close()
        return {}

    print("=" * 60)
    print("GENERATING RESOLUTION OPTIONS")
    print("=" * 60)
    print(f"Analyzing {len(group_ids)} clash groups...\n")

    results = {}

    for i, group_id in enumerate(group_ids, 1):
        print(f"Group {i}/{len(group_ids)}: {group_id}")
        options = engine.analyze_group(group_id)
        results[group_id] = options

        if options:
            for opt in options:
                print(f"  ✓ Option {opt.rank}: {opt.description[:60]}...")
                print(f"    Design Effort: {opt.total_design_hours:.1f} hrs (${opt.total_design_cost:,.0f})")
                print(f"    Schedule: {opt.calendar_days:.0f} days")
                print(f"    Risk: {opt.risk_category}")
        else:
            print(f"  ⚠ No applicable resolution options generated")
        print()

    engine.close()

    print("=" * 60)
    print(f"✓ Analysis complete: {sum(len(opts) for opts in results.values())} total options generated")
    print("=" * 60)

    return results


if __name__ == "__main__":
    """
    Generate resolution options for all Terminal 1 clash groups
    """
    import sys

    db_path = "/home/red1/Documents/bonsai/DatabaseFiles/clash_status.db"

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    results = analyze_all_groups(db_path)

    # Summary
    total_options = sum(len(opts) for opts in results.values())

    if total_options > 0:
        print("\n" + "=" * 60)
        print("NEXT STEPS")
        print("=" * 60)
        print("1. Review options in database: resolution_options table")
        print("2. Implement UI to display options to users")
        print("3. Add user selection tracking to resolution_history table")
        print("4. Build learning system from actual vs estimated outcomes")
