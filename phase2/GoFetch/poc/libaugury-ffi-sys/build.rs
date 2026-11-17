use cc;

fn main() {
    let src = [
        "src/c_augury.c"
    ];

    let mut builder = cc::Build::new();
    let build = builder
        .files(src.iter())
        .include("src")
        .static_flag(true);

    // Hardcoding the Darwin target triple here used to force every build
    // (macOS or not) through the Apple Clang frontend. On Linux, let `cc`
    // infer the host target (aarch64-unknown-linux-gnu via gcc) instead of
    // cross-targeting Darwin, which would either invoke a nonexistent
    // cross-compiler or pass Darwin-only flags to a Linux cc/gcc.
    #[cfg(target_os = "macos")]
    build.target("aarch64-apple-darwin");

    build.compile("augury-ffi");
}
