# Generic single-clock constraints. The clock period (ns) comes from the
# CLK_PERIOD_NS environment variable (default 20 ns), so a frequency sweep
# does not need a new file per point. I/O delays are 20 % of the period.
set clk_period 20.0
if {[info exists ::env(CLK_PERIOD_NS)]} { set clk_period $::env(CLK_PERIOD_NS) }
set clk_io_pct 0.2

create_clock -name core_clock -period $clk_period [get_ports clk]
set non_clock_inputs [all_inputs -no_clocks]
set_input_delay  [expr {$clk_period * $clk_io_pct}] -clock core_clock $non_clock_inputs
set_output_delay [expr {$clk_period * $clk_io_pct}] -clock core_clock [all_outputs]
