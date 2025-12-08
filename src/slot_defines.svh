// Maximum pad counts based on physical slot dimensions.
// These define the maximum number of each pad type that can physically fit.
// Actual configs may use fewer pads.
//
// Physical limits per slot (IO cell = 75um, corner = 355um):
// - 1x1:     N/S=42 pads, E/W=58 pads, total=200
// - 0.5x1:   N/S=16 pads, E/W=58 pads, total=148
// - 1x0.5:   N/S=42 pads, E/W=24 pads, total=132
// - 0.5x0.5: N/S=16 pads, E/W=24 pads, total=80

`ifdef SLOT_1X1

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 15
`define NUM_DVSS_PADS 15

// Signal pads (max physical - clk - rst - power)
`define NUM_INPUT_PADS 0
`define NUM_BIDIR_PADS 168
`define NUM_ANALOG_PADS 0

`endif

`ifdef SLOT_0P5X1

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 11
`define NUM_DVSS_PADS 11

// Signal pads
`define NUM_INPUT_PADS 0
`define NUM_BIDIR_PADS 124
`define NUM_ANALOG_PADS 0

`endif

`ifdef SLOT_1X0P5

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 10
`define NUM_DVSS_PADS 10

// Signal pads
`define NUM_INPUT_PADS 0
`define NUM_BIDIR_PADS 110
`define NUM_ANALOG_PADS 0

`endif

`ifdef SLOT_0P5X0P5

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 6
`define NUM_DVSS_PADS 6

// Signal pads
`define NUM_INPUT_PADS 0
`define NUM_BIDIR_PADS 66
`define NUM_ANALOG_PADS 0

`endif
