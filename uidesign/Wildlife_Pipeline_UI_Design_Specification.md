# Wildlife Pipeline UI Design Specification

**Author:** Yifan Wu  
**Date:** February 2026  
**Version:** Wireframe v3

---

## Overall Design Principles

When designing this system, I focused on one core principle: making it easy for non-technical users to use. Since the primary users are Julie (UCI Campus Reserves Manager) and student interns, they care more about "getting the job done" than understanding technical details. Therefore, I used a clear visual hierarchy, intuitive icons, and minimal text so users can quickly find what they need.

For the color palette, I selected UCI's official blue (#0064A4) and gold (#FFD200) as the primary colors to reflect campus identity and stay aligned with the UCI Nature brand. The logo in the wireframe is for placeholder purposes only; it will be adjusted based on the partner's requirements.

---

## Login Page

**Design rationale:**

The login page is the user's first impression, so I wanted it to feel both professional and approachable. The left panel uses a deep blue background with a brief feature overview, helping users understand what the system does before signing in. The right panel contains a clean, simple login form to reduce cognitive load.

I included two login options:
- **Traditional username/password:** suitable for external collaborators or guest accounts
- **UCI NetID login:** one-click login for campus users, avoiding password management

The "Remember me" option supports daily use—if Julie uses the system frequently, she shouldn't have to re-enter credentials each time. If the system needs to integrate directly with the university's official login page, this can be adjusted later.

---

## Logout

**Design rationale:**

The logout button is placed on the far right of the top status bar, next to the user avatar. I used an icon instead of text to save space and keep the interface clean. On hover, the icon turns red to provide feedback and signal that this is an action that should be taken with care.

This placement follows common web app conventions (e.g., Gmail, Slack), so users can find it without needing to learn a new pattern.

---

## Sidebar Navigation

**Design rationale:**

The navigation items follow the natural workflow order: Upload → Run Model → Review → Validate → Export. This encourages users to work top-to-bottom without unnecessary back-and-forth.

**Collapse/expand behavior:**

To support smaller screens (e.g., laptops), the sidebar can collapse to icon-only mode. When collapsed, hovering over an icon shows a tooltip with the feature name, ensuring users do not lose orientation.

---

## Dashboard

**Design rationale:**

The dashboard is the first page after login and must answer one key question: "What is the overall status right now?"

### Top KPI Cards (5)
- **Total Images:** communicates overall data scale
- **Processed:** shows progress completion
- **Animals Detected:** highlights the most important outcome
- **Pending Review:** indicates remaining review workload
- **Warnings:** flags issues that need attention (in red)

### Processing Progress

The progress bar spans the full width and uses arrows to connect each stage, visually presenting the pipeline as a continuous flow. Users can immediately see where the process is "stuck." Adding Export as the final step clarifies the endpoint of the workflow.

### Run Summary & Species Distribution

These two panels appear side-by-side: the left answers "how the system is running," while the right answers "what we are finding."

- **Run Summary** uses a circular gauge to show success rate since it is a percentage and the circular form is intuitive. Detailed metrics (time, counts, throughput) are presented as a simple text list to avoid chart complexity.
- **Species Distribution** uses a donut chart instead of a pie chart; the center space displays the total count for a more modern look. Each species uses a distinct color, and the legend includes both count and percentage to support different reading preferences.

---

## Upload

**Design rationale:**

Two upload options support different scenarios:
- **Google Drive sync (primary):** processing 100,000+ images cannot rely on manual upload
- **Manual drag-and-drop:** for small, temporary uploads or testing

A camera/location list at the bottom lets users see data sources clearly and filter sync by location. Using real UCI reserve names (e.g., Research Park, San Joaquin Marsh) adds professionalism and familiarity.

---

## Run Model

**Design rationale:**

This page centers around a large "Run Model" button. Julie does not need to understand MegaDetector's technical details—she only needs to start the run and wait for completion.

### Help design for Settings

I recognized that Confidence Threshold and Batch Size may be unfamiliar to non-technical users, so I added help icons:

- **Blue question mark (?)** for Confidence Threshold: explains that a higher threshold reduces false positives but may increase missed detections
- **Yellow exclamation mark (!)** for Batch Size: a caution message that selecting "All images" may require significant memory

These icons are intentionally minimal: they do not clutter the interface, but they provide guidance when needed. This balances usability—avoiding long explanations while preventing blind configuration.

### Recent Runs table

Run history helps users track "how many images were processed last time" and supports comparison and verification. The Status column uses color to indicate success, failure, or partial completion.

---

## Review & Modify

**Design rationale:**

This page implements the partner's required "modify" function. Since ML models can make mistakes, manual review is necessary.

It uses a standard two-column layout:
- **Left:** image list with search and filters
- **Right:** large preview + edit form

A "Needs Review" label is highlighted in orange to prioritize low-confidence images. The small orange dot acts as subtle visual emphasis without disrupting browsing.

The three action buttons at the bottom—Confirm / Skip / Flag Issue—cover the full set of likely actions: confirm correctness, defer for later, or flag an issue for discussion.

---

## Validate

**Design rationale:**

This page maps directly to the sprint goal of "validate data" and "catch missing or broken rows." The design follows a "summary → details" hierarchy:

- **Top summary cards:** four quick health metrics
- **Checklist:** each validation rule with result indicators (✓ / ⚠ / ✗)
- **Issues table:** specific issues + one-click fix actions

Buttons such as "Auto-fix from filename" are essential: the UI should not only report problems, but also provide solutions. This reduces user steps and decision load.

---

## Export

**Design rationale:**

Export is the endpoint of the workflow—users need to take the results out of the system.

### Quick export options (3)

Presets cover the most common export scenarios so users do not need to configure filters every time:
- **Full Dataset:** all data
- **Animals Only:** only images containing animals
- **Needs Review:** export items for review by others

### Filters

For advanced needs, full filtering is available. The date picker uses a consistent English format to match the rest of the system.

### Export History

Export history allows users to re-download previous exports without reconfiguring parameters.

---

## Next Steps

This wireframe covers all core functions required by the partner. Next, the plan is to:
- Collect feedback from teammates and the partner
- Refine the design based on feedback
- Move into the prototype phase to implement realistic interactions

If you have any questions or suggestions, feel free to reach out anytime.
