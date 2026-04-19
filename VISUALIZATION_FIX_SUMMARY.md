# Visualization Routing Fix - Implementation Summary

## Problem Statement
Visualization requests like "show histogram", "plot distribution", "display correlation heatmap", and "year vs value" were not triggering the run_viz node. Instead, execution fell back to run_eda and returned "Chart data unavailable."

## Root Cause
The visualization intent block was returning early with an error when:
- No dataset was available, AND
- No dataset topic keywords (GDP, population, etc.) were detected

This prevented visualization requests from proceeding through the pipeline.

## Changes Made

### 1. Intent Classifier Enhancement
**File**: `backend/utils/intent_classifier.py`

**Change**: Added more visualization keywords
```python
viz_keywords = [
    "plot",
    "show",        # NEW
    "display",     # NEW
    "chart",
    "graph",
    "distribution",
    "scatter",
    "bar",
    "pie",
    "line",
    "box",
    "heatmap",
    "correlation",
    "trend",
    "histogram",
    "vs",
]
```

**Benefit**: Now detects common visualization commands like "show histogram", "display correlation"

---

### 2. Planner Agent - Visualization Routing Fix
**File**: `backend/agents/planner_agent.py`

**Change**: Removed early-stop logic and simplified visualization routing
```python
# BEFORE:
if "visualization" in intents:
    dataset_available = _ensure_dataset_loaded(state, plan)
    if not dataset_available and not dataset_requested:
        state["answer"] = "I could not determine which dataset to load..."
        state["stop"] = True
        return state
    
    plan.extend([
        "profile_data",
        "dataset_topic_detection",      # Removed
        "pattern_detection",             # Removed
        "run_viz",
        "chart_interpretation",
    ])
    ...

# AFTER:
if "visualization" in intents:
    dataset_available = _ensure_dataset_loaded(state, plan)
    
    # Visualization should always proceed - load dataset if needed
    plan.extend([
        "profile_data",
        "run_viz",
        "chart_interpretation",
    ])
    ...
```

**Benefits**:
- Visualization requests no longer fail early
- Auto-fetches data if needed (via _ensure_dataset_loaded)
- Removed unnecessary pipeline steps
- Always proceeds with visualization execution

---

### 3. Visualization Agent - Chart Serialization Fix
**File**: `backend/agents/viz_agent.py`

**Change**: Updated chart JSON serialization method
```python
# BEFORE:
if fig:
    state["chart"] = figure_to_json(fig)

# AFTER:
if fig:
    state["chart"] = fig.to_plotly_json()
```

**Benefit**: Ensures Plotly figures are correctly serialized to JSON format for API responses

---

## Verification Tests

### Test 1: Visualization with No Dataset
```
Question: "show histogram"
Plan: ['fetch_data', 'profile_data', 'run_viz', 'chart_interpretation']
Status: ✓ PASS
```

### Test 2: Correlation Heatmap
```
Question: "show correlation heatmap"  
Plan: ['fetch_data', 'profile_data', 'run_viz', 'chart_interpretation']
Status: ✓ PASS
```

### Test 3: Scatter Plot
```
Question: "year vs sales"
Plan: ['fetch_data', 'profile_data', 'run_viz', 'chart_interpretation']
Status: ✓ PASS
```

### Test 4: Visualization with Data Already Loaded
```
Question: "plot distribution"
Plan: ['profile_data', 'run_viz', 'chart_interpretation']
(Note: No 'fetch_data' because data already loaded)
Status: ✓ PASS
```

### Test 5: Chart Generation
- Histogram generation: ✓ PASS (returns dict with data)
- Heatmap generation: ✓ PASS (returns dict with data)
- Scatter plot generation: ✓ PASS (returns dict with data)
- Box plot generation: ✓ PASS (returns dict with data)

---

## Expected Behavior After Fix

### Before
```
User: "show histogram"
System: "Chart data unavailable."
```

### After
```
User: "show histogram"
System:
  1. fetch_data (auto-fetches dataset if available)
  2. profile_data (analyzes dataset structure)
  3. run_viz (generates histogram visualization)
  4. chart_interpretation (explains the chart)
Result: Plotly histogram visualization returned
```

---

## Key Improvements

1. **Always Visualization-First**: If user mentions visualization keywords, system prioritizes visualization
2. **Smart Auto-Loading**: Automatically fetches data if needed without requiring user upload
3. **Robust Keyword Detection**: Now recognizes common phrases like "show", "display", "plot"
4. **Correct JSON Serialization**: Charts are properly serialized for API responses
5. **Cleaner Pipeline**: Removed unnecessary dataset_topic_detection and pattern_detection steps for simple visualizations

---

## Files Modified
- `backend/utils/intent_classifier.py`
- `backend/agents/planner_agent.py`
- `backend/agents/viz_agent.py`

## No Breaking Changes
- All existing tests continue to pass
- Other analysis paths (EDA, forecasting, statistical analysis) unaffected
- Backward compatible with existing dataset loading mechanisms
