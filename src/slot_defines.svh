// Pad counts for different slot sizes and configurations.
//
// Two configuration types are supported:
// - DEF (default): Mixed pad types (bidir, input, analog) from original configs
// - MAX/SPC/NUM: All bidir pads for maximum signal count (define MAX_IO_CONFIG)
//
// Physical limits per slot (IO cell = 75um, corner = 355um, seal ring = 26um):
// - 1x1:     N/S=42 pads, E/W=58 pads, total=200
// - 0.5x1:   N/S=15 pads, E/W=58 pads, total=146
// - 1x0.5:   N/S=42 pads, E/W=23 pads, total=130
// - 0.5x0.5: N/S=15 pads, E/W=23 pads, total=76

`ifdef SLOT_1X1

`ifdef NUM_DVDD_PADS_OVERRIDE
  `define NUM_DVDD_PADS `NUM_DVDD_PADS_OVERRIDE
`else
  `define NUM_DVDD_PADS 8
`endif
`ifdef NUM_DVSS_PADS_OVERRIDE
  `define NUM_DVSS_PADS `NUM_DVSS_PADS_OVERRIDE
`else
  `define NUM_DVSS_PADS 10
`endif

`ifdef MAX_IO_CONFIG
  // Maximum bidir configuration - no input/analog pads
  `define NUM_INPUT_PADS 0
  `ifdef NUM_BIDIR_PADS_OVERRIDE
    `define NUM_BIDIR_PADS `NUM_BIDIR_PADS_OVERRIDE
  `else
    `define NUM_BIDIR_PADS 168
  `endif
  `define NUM_ANALOG_PADS 0
`else
  // Default configuration - mixed pad types from original slot_1x1.yaml
  `define NUM_INPUT_PADS 12
  `define NUM_BIDIR_PADS 40
  `define NUM_ANALOG_PADS 2
`endif

`endif

`ifdef SLOT_0P5X1

`ifdef NUM_DVDD_PADS_OVERRIDE
  `define NUM_DVDD_PADS `NUM_DVDD_PADS_OVERRIDE
`else
  `define NUM_DVDD_PADS 8
`endif
`ifdef NUM_DVSS_PADS_OVERRIDE
  `define NUM_DVSS_PADS `NUM_DVSS_PADS_OVERRIDE
`else
  `define NUM_DVSS_PADS 8
`endif

`ifdef MAX_IO_CONFIG
  // Maximum bidir configuration - no input/analog pads
  `define NUM_INPUT_PADS 0
  `ifdef NUM_BIDIR_PADS_OVERRIDE
    `define NUM_BIDIR_PADS `NUM_BIDIR_PADS_OVERRIDE
  `else
    `define NUM_BIDIR_PADS 122
  `endif
  `define NUM_ANALOG_PADS 0
`else
  // Default configuration - mixed pad types from original slot_0p5x1.yaml
  `define NUM_INPUT_PADS 4
  `define NUM_BIDIR_PADS 44
  `define NUM_ANALOG_PADS 6
`endif

`endif

`ifdef SLOT_1X0P5

`ifdef NUM_DVDD_PADS_OVERRIDE
  `define NUM_DVDD_PADS `NUM_DVDD_PADS_OVERRIDE
`else
  `define NUM_DVDD_PADS 8
`endif
`ifdef NUM_DVSS_PADS_OVERRIDE
  `define NUM_DVSS_PADS `NUM_DVSS_PADS_OVERRIDE
`else
  `define NUM_DVSS_PADS 8
`endif

`ifdef MAX_IO_CONFIG
  // Maximum bidir configuration - no input/analog pads
  `define NUM_INPUT_PADS 0
  `ifdef NUM_BIDIR_PADS_OVERRIDE
    `define NUM_BIDIR_PADS `NUM_BIDIR_PADS_OVERRIDE
  `else
    `define NUM_BIDIR_PADS 108
  `endif
  `define NUM_ANALOG_PADS 0
`else
  // Default configuration - mixed pad types from original slot_1x0p5.yaml
  `define NUM_INPUT_PADS 4
  `define NUM_BIDIR_PADS 46
  `define NUM_ANALOG_PADS 4
`endif

`endif

`ifdef SLOT_0P5X0P5

`ifdef NUM_DVDD_PADS_OVERRIDE
  `define NUM_DVDD_PADS `NUM_DVDD_PADS_OVERRIDE
`else
  `define NUM_DVDD_PADS 4
`endif
`ifdef NUM_DVSS_PADS_OVERRIDE
  `define NUM_DVSS_PADS `NUM_DVSS_PADS_OVERRIDE
`else
  `define NUM_DVSS_PADS 4
`endif

`ifdef MAX_IO_CONFIG
  // Maximum bidir configuration - no input/analog pads
  `define NUM_INPUT_PADS 0
  `ifdef NUM_BIDIR_PADS_OVERRIDE
    `define NUM_BIDIR_PADS `NUM_BIDIR_PADS_OVERRIDE
  `else
    `define NUM_BIDIR_PADS 62
  `endif
  `define NUM_ANALOG_PADS 0
`else
  // Default configuration - mixed pad types from original slot_0p5x0p5.yaml
  `define NUM_INPUT_PADS 4
  `define NUM_BIDIR_PADS 38
  `define NUM_ANALOG_PADS 4
`endif

`endif
