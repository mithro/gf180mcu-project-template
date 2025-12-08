// Pad counts supporting both default and maximum density configurations.
// Default configs have mixed pad types (bidir, input, analog).
// Max configs use all bidir pads for maximum signal count.
// Each count is the maximum needed across all config variants.
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

// Signal pads - supports both def (mixed) and max (all bidir) configs
`define NUM_INPUT_PADS 12
`define NUM_BIDIR_PADS 168
`define NUM_ANALOG_PADS 2

`endif

`ifdef SLOT_0P5X1

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 11
`define NUM_DVSS_PADS 11

// Signal pads - supports both def (mixed) and max (all bidir) configs
`define NUM_INPUT_PADS 4
`define NUM_BIDIR_PADS 124
`define NUM_ANALOG_PADS 6

`endif

`ifdef SLOT_1X0P5

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 10
`define NUM_DVSS_PADS 10

// Signal pads - supports both def (mixed) and max (all bidir) configs
`define NUM_INPUT_PADS 4
`define NUM_BIDIR_PADS 110
`define NUM_ANALOG_PADS 4

`endif

`ifdef SLOT_0P5X0P5

// Power/ground pads for core and I/O
`define NUM_DVDD_PADS 6
`define NUM_DVSS_PADS 6

// Signal pads - supports both def (mixed) and max (all bidir) configs
`define NUM_INPUT_PADS 4
`define NUM_BIDIR_PADS 66
`define NUM_ANALOG_PADS 4

`endif
