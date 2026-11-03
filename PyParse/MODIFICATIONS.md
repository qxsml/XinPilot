# Original PyParse: restoration record

On 2 November 2026 the five original engine files were restored byte-for-byte to
the pinned upstream commit recorded in [PROVENANCE.md](PROVENANCE.md).
There are no XinPilot modifications in those engine files.

This removes the earlier template-loader and string-preserving CSV adaptations,
the added XinPilot modification comment, and the recent pie-chart/exit-status
fixes. Upstream author, copyright and license text remains intact.

Failure detection and the analysis-failed UI are implemented in XinPilot's
runner, outside PyParse. The original empty-pie error is not repaired locally.
The separate [Modified PyParse](../Modified%20PyParse/MODIFICATIONS.md) engine
and its modification notices are unchanged.
