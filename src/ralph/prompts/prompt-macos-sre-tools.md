Build a production-ready set of macOS security research tools (`macos-sre`):

1. Include 5 distinct tools, each focusing on a different part of the operating system - don't go for the most obvious ideas e.g. reporting users, network extensions, sandboxing, things based on codesigning. I want to use this project to learn so come up with some less well-known APIs to surface. I like userspace-related tools so avoid iokit, kexts and so on.
2. Ensure all tools are thoroughly tested as a human would do, that they return useful information when run on macOS with no fields/parts missing, malformed, unknown or difficult for a human to read.
3. Tools should have obvious CLIs and clear documentation for human use. Don't do tables/ascii art/aggressive use of colours
4. Each tool should include an `--how` flag that explains how the tool works to a security researcher (which tools/APIs it calls, with example calls, how they work, any limitations/things that might work differently on iOS)
