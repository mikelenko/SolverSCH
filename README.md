# SolverSCH - Autonomous EDA Designer

An industrial-grade Autonomous Electronic Design Automation (EDA) framework. It features a native MNA physics engine, an AI-driven optimization loop, and professional sign-off verification.

## Core Features
1. **MNA Physics Core**: $O(1)$ performance mathematical solver with `Gmin` injection for unconditional stability.
2. **Autonomous Designer**: LLM-driven optimization loop that iterates components until targets are met.
3. **LTspice Sign-off**: Industrial-grade verification layer using `PyLTSpice` for bit-accurate results.
4. **Professional Documentation Layer**: Generates high-quality vector engineering schematics via `SchemDraw`.

## Quick Start
```bash
# Run a design task
python -m solver_sch.ai.auto_designer "[DC TARGET: 6V] Design a divider from 12V source."
```

## Architecture
- `solver_sch/solver/`: Sparse matrix solvers and NR iteration logic.
- `solver_sch/ai/`: The brain of the designer.
- `solver_sch/utils/pro_visualizer.py`: Scientific documentation layer.
