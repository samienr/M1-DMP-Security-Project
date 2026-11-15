// Linux/Asahi replacement for `dyld_search.rs`.
//
// What the macOS original does: it runs `vmmap <own pid>` and scans *its
// own* process's memory map for a run of `.dylib`/`dyld` mappings at least
// 200 pages long. It can get away with inspecting only its own address
// space because macOS's dyld shared cache is mapped at (almost always) the
// same virtual address in *every* process on the machine until the next
// reboot -- so "valid in my own map" implies "valid in the victim's map
// too," with zero cross-process introspection.
//
// Linux has no equivalent of a single shared, cross-process-identical
// cache. The nearest substitute: with ASLR disabled for a given process
// (`personality(ADDR_NO_RANDOMIZE)`, set here via the `setarch -R` wrapper
// at launch -- no root needed), the dynamic linker's placement of shared
// libraries becomes deterministic, and -- confirmed empirically on this
// machine -- *that* placement is independent of which binary is running,
// as long as the binary's dynamic dependency list is the same. Our
// attacker and victim are both plain Rust binaries with no extra C deps
// beyond glibc, so their library layout coincides.
//
// So, like the original, this only ever looks at the *calling* process's
// own /proc/self/maps -- it is run by (or as) the attacker, under
// `setarch $(uname -m) -R`, and trusts that the same region is mapped at
// the same address in the victim (also launched under `setarch -R`).
//
// Fidelity note for the writeup: this is a weaker assumption than the
// macOS original. dyld-cache sharing holds for *any* two macOS processes
// unconditionally; our ASLR-off trick only holds between processes with
// matching dynamic dependency lists, which we control here but a real
// blind attacker normally wouldn't. Call this out explicitly as a known
// reduced-fidelity substitution, not an equivalent technique.
use std::fs;

fn main() {
    let maps = fs::read_to_string("/proc/self/maps")
        .expect("failed to read /proc/self/maps");

    // Merge all contiguous VMAs backed by the same shared library file
    // (libc.so's r-xp/---p/r--p/rw-p segments are laid out back-to-back
    // with no gap, confirmed on this machine) into one [start, end) span
    // per library, then keep whichever span is largest.
    let mut best: Option<(u64, u64, String)> = None;
    let mut cur: Option<(u64, u64, String)> = None;

    for line in maps.lines() {
        // Format: "<start>-<end> <perms> <offset> <dev> <inode>  <path>"
        let mut parts = line.splitn(6, ' ').filter(|s| !s.is_empty());
        let addr_range = match parts.next() {
            Some(s) => s,
            None => continue,
        };
        let path = line.rsplit(' ').next().unwrap_or("").trim();
        if path.is_empty() || !path.contains(".so") {
            cur = None;
            continue;
        }

        let (start_s, end_s) = match addr_range.split_once('-') {
            Some(p) => p,
            None => continue,
        };
        let start = u64::from_str_radix(start_s, 16).unwrap();
        let end = u64::from_str_radix(end_s, 16).unwrap();

        match &cur {
            Some((_, cur_end, cur_path)) if *cur_end == start && cur_path == path => {
                cur = Some((cur.unwrap().0, end, path.to_string()));
            }
            _ => {
                cur = Some((start, end, path.to_string()));
            }
        }

        let span = cur.as_ref().unwrap();
        let span_len = span.1 - span.0;
        let best_len = best.as_ref().map(|b| b.1 - b.0).unwrap_or(0);
        if span_len > best_len {
            best = cur.clone();
        }
    }

    let (victim_cl_start, victim_cl_end, path) = best.expect(
        "no shared-library mapping found in /proc/self/maps -- was this run under `setarch $(uname -m) -R`?",
    );

    let span_pages = (victim_cl_end - victim_cl_start) / 16384;
    println!("[+] Largest shared-library span: {} ({} pages)", path, span_pages);
    println!("[+] Target Pointer start frame -> {:#x}", victim_cl_start);
    println!("[+] Target Pointer end frame -> {:#x}", victim_cl_end);
    if span_pages < 50 {
        println!(
            "[!] WARNING: span is only {} pages -- original macOS dyld_search required >=200. \
            Search space for the attack gadget will be small; consider also whether ASLR is \
            really off (personality(ADDR_NO_RANDOMIZE)) for this process.",
            span_pages
        );
    }

    fs::write(
        "dyld_space.txt",
        format!("{:#x}\n{:#x}\n", victim_cl_start, victim_cl_end),
    )
    .unwrap();
}
