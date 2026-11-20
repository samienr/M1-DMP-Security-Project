// Calibrate pp_threshold for this machine's CounterTimer, instead of
// reusing the GoFetch README's macOS example value (680) unchanged.
//
// Reuses the project's own eviction-set generation (evict_rs) and the
// exact same CounterTimer/Prime+Probe primitives ctswap_attacker.rs uses,
// so the measured cached/evicted distributions are directly comparable
// to what the real attack sees.
use libaugury_ffi_sys::pin_cpu;
use std::env::args;
use std::fs::File;
use std::io::Write;
use mmap_rs::MmapOptions;
use rand::thread_rng;
use evict_rs::timer::Timer;
use evict_rs::MyTimer;
use evict_rs::allocator::Allocator;
use evict_rs::eviction_set_generation;
use evict_rs::eviction_set::EvictionSet;
use evict_rs::NATIVE_PAGE_SIZE;

const MB: usize = 1024 * 1024;

fn main() {
    let samples: usize = args().nth(1)
        .map(|s| s.parse().unwrap())
        .unwrap_or(300);

    unsafe { pin_cpu(4); }
    let timer = MyTimer::new();

    // Same victim-pool setup as eviction_set_gen64 (evict-rs/src/lib.rs).
    let victim_size: usize = (12 * MB + 128 * 1024) * 8;
    let mut victim_mmap = MmapOptions::new(victim_size + 128)
        .map_mut()
        .unwrap();
    let bytes = unsafe {
        core::slice::from_raw_parts_mut(victim_mmap.as_mut_ptr() as *mut u8, victim_mmap.len())
    };
    bytes.fill(0xff);
    let victim_ptr = victim_mmap.as_mut_ptr() as *mut u8;

    let mut allocator = Allocator::new(0, NATIVE_PAGE_SIZE);
    println!("[+] Generating a real, reduced L2 eviction set for calibration...");
    let eviction_set = eviction_set_generation(victim_ptr, &mut allocator, &timer)
        .expect("eviction set generation failed");
    println!("[+] Got eviction set with {} cache lines", eviction_set.cache_lines.len());

    let mut rng = thread_rng();
    let es = EvictionSet::new(&eviction_set.cache_lines);

    let mut cached = Vec::with_capacity(samples);
    let mut evicted = Vec::with_capacity(samples);

    println!("[+] Collecting {} cached + {} evicted samples...", samples, samples);
    for _ in 0..samples {
        // Cached: load victim, then immediately time a second load (no
        // eviction-set traversal in between) -- same timer, same victim,
        // just skipping the self.access() eviction attempt.
        unsafe { victim_ptr.read_volatile() };
        unsafe { core::arch::asm!("dsb ish") };
        unsafe { core::arch::asm!("isb sy") };
        let t = timer.time_load(victim_ptr);
        cached.push(t);

        // Evicted: the real mechanism ctswap_attacker.rs uses.
        let t = es.evict_and_time_once(&timer, victim_ptr);
        evicted.push(t);
        let _ = &mut rng; // keep for parity with evict_and_time's own rng usage pattern
    }

    let mut f = File::create("calibration_samples.csv").unwrap();
    writeln!(f, "cached,evicted").unwrap();
    for i in 0..samples {
        writeln!(f, "{},{}", cached[i], evicted[i]).unwrap();
    }
    println!("[+] Wrote calibration_samples.csv");
}
