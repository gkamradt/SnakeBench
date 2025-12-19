# TrueSkill Skill Analysis

## Overview

The Skill Analysis page provides interactive visualizations for exploring TrueSkill ratings of AI models competing in SnakeBench. It helps users understand model performance beyond simple win/loss ratios.

## Features

### Bell Curve Visualizations
- **Gaussian distributions** showing skill estimate (mu) and uncertainty (sigma)
- **Reference model overlay** for visual comparison between two models
- **Confidence intervals** displaying pessimistic (mu - 3*sigma) and optimistic (mu + 3*sigma) bounds

### Confidence Intervals
- **99.7% confidence interval** (3-sigma) showing the range where true skill likely falls
- **Pessimistic rating** - conservative lower bound used for leaderboard ranking
- **Optimistic rating** - upper bound representing best-case skill estimate

### Win Probability Calculator
- **Head-to-head probability** calculation using TrueSkill formula
- **LaTeX formula display** showing the mathematical basis
- **Role-based color coding** (blue for compare model, green for baseline)

### Interactive Scatter Plot
- **Mu/Sigma plane** visualization of all models
- **Click to select** models for comparison
- **Hover tooltips** showing model details
- **Keyboard accessible** with focus states

### Multi-Curve Overlay
- **Compare up to 5 models** simultaneously
- **Color-coded legend** with model statistics
- **Hover highlighting** to focus on individual curves

## Usage

### Navigation
Access the Skill Analysis page via:
- Navbar link: "Skill Analysis"
- Direct URL: `/skill-analysis`

### URL Parameters
The page supports shareable URLs with model selections:
- `?model=<slug>` - Pre-select the compare model
- `?reference=<slug>` - Pre-select the baseline model

Example: `/skill-analysis?model=openai/gpt-4&reference=anthropic/claude-3`

### Poster View
1. Select a **Compare Model** from the left panel (sorted by games played)
2. Select a **Baseline Model** from the right panel (sorted by win rate)
3. View the bell curve, metrics, and win probability

### Comparison View
1. Switch to the "Comparison View" tab
2. Click dots in the scatter plot to select models (up to 5)
3. View overlapping bell curves in the multi-curve chart
4. Hover over curves or legend items to highlight

## Technical Details

### TrueSkill Parameters
- **mu (skill estimate)**: Center of the skill distribution (default: 25.0)
- **sigma (uncertainty)**: Standard deviation of the distribution (default: 8.333)
- **exposed (conservative rating)**: mu - 3*sigma, used for ranking
- **beta**: Skill chain length (default: mu/6 = 4.167)
- **tau**: Dynamics factor for rating drift (default: 0.5)
- **draw_probability**: Expected draw rate (default: 0.1)

### Win Probability Formula
```
P(model1 beats model2) = Phi((mu1 - mu2) / sqrt(sigma1^2 + sigma2^2))
```
Where Phi is the standard normal CDF.

### Backend Architecture

The TrueSkill calculations are performed server-side in the Flask backend:

1. **`services/trueskill_engine.py`** - Core rating engine
   - Uses Microsoft's `trueskill` Python library
   - `TrueSkillEngine.rate_game(game_id)` processes match results
   - Computes new mu/sigma for each participant based on match outcome
   - Accounts for opponent strength (beating a strong opponent = bigger gain)

2. **`data_access/repositories/model_repository.py`** - Database persistence
   - `update_trueskill_batch()` writes ratings to `models` table
   - Columns: `trueskill_mu`, `trueskill_sigma`, `trueskill_exposed`, `trueskill_updated_at`

3. **`cli/backfill_trueskill.py`** - Historical recalculation
   - Replays all games chronologically to rebuild ratings
   - Use `--reset` flag to start fresh from defaults
   - Supports `--dry-run` for testing

### Data Source
The frontend fetches from Flask `/api/stats?simple=true`, which returns:
```json
{
  "totalGames": 12345,
  "aggregatedData": {
    "model-slug": {
      "trueskill_mu": 28.5,
      "trueskill_sigma": 2.1,
      "trueskill_exposed": 22.2,
      "wins": 150,
      "losses": 80,
      "ties": 20,
      "games_played": 250,
      "total_cost": 1.23
    }
  }
}
```

## Dependencies

- **react-katex**: LaTeX math rendering
- **@radix-ui/react-***: UI primitives (accordion, tabs, tooltip, scroll-area)
- **TailwindCSS**: Styling

## File Structure

```
frontend/src/
  app/skill-analysis/
    page.tsx              # Server Component (data fetching)
    SkillAnalysisClient.tsx  # Client Component (interactivity)
  components/skill-analysis/
    SkillDistributionChart.tsx  # Bell curve SVG
    SkillMetrics.tsx            # Mu/sigma badges
    WinProbability.tsx          # Win probability display
    SkillScatterPlot.tsx        # Interactive scatter plot
    MultiCurveOverlay.tsx       # Multi-model comparison
  lib/
    confidenceIntervals.ts  # Gaussian math utilities
    winProbability.ts       # Win probability calculations
    roleColors.ts           # Color constants
    api/trueskill.ts        # Data fetching functions
  types/
    trueskill.ts            # TypeScript interfaces
```

## Credits

Visualization code adapted from the [arc-explainer](https://github.com/82deutschmark/arc-explainer) project's Worm Arena skill analysis feature.
