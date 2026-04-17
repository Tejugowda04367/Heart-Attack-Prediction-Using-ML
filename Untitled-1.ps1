# ============================
#   Simple NS2 Network Script
# ============================

# Create simulator object
set ns [new Simulator]

# Open trace files
set tracefile [open out.tr w]
$ns trace-all $tracefile

set namfile [open out.nam w]
$ns namtrace-all $namfile

# Create two nodes
set n0 [$ns node]
set n1 [$ns node]

# Create duplex link between nodes
$ns duplex-link $n0 $n1 1Mb 10ms DropTail

# Create a UDP agent and attach to n0
set udp0 [new Agent/UDP]
$ns attach-agent $n0 $udp0

# Create Null agent (sink) at n1
set null0 [new Agent/Null]
$ns attach-agent $n1 $null0

# Connect UDP to Null
$ns connect $udp0 $null0

# Create Application (CBR traffic)
set cbr0 [new Application/Traffic/CBR]
$cbr0 set packetSize_ 512
$cbr0 set interval_ 0.010
$cbr0 attach-agent $udp0

# Start / Stop times
$ns at 0.5 "$cbr0 start"
$ns at 4.5 "$cbr0 stop"

# Finish procedure
proc finish {} {
    global ns tracefile namfile
    $ns flush-trace
    close $tracefile
    close $namfile
    exec nam out.nam &
    exit 0
}

# Call finish at time 5.0
$ns at 5.0 "finish"

# Run simulation
$ns run