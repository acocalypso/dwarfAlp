// Decompile explicitly selected functions and their direct call neighbors.
// @category DWARF

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

public class ExportSelectedDecompilation extends GhidraScript {
    private static final int DECOMPILE_TIMEOUT_SECONDS = 30;

    private static String clean(String value) {
        return value.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ');
    }

    private static boolean usable(Function function) {
        return function != null && !function.isExternal() && !function.isThunk();
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "expected output directory and comma-separated addresses");
        }

        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create output directory: " + outputDirectory);
        }

        FunctionManager functions = currentProgram.getFunctionManager();
        Set<Function> selected = new TreeSet<>(Comparator.comparing(Function::getEntryPoint));
        Map<Function, String> roles = new LinkedHashMap<>();

        for (String text : args[1].split(",")) {
            Address address = currentProgram.getAddressFactory().getAddress(text.trim());
            if (address == null) {
                throw new IllegalArgumentException("invalid address: " + text);
            }
            Function seed = functions.getFunctionAt(address);
            if (seed == null) {
                seed = functions.getFunctionContaining(address);
            }
            if (!usable(seed)) {
                throw new IllegalArgumentException("no internal function at address: " + text);
            }
            selected.add(seed);
            roles.put(seed, "seed");

            for (Function caller : seed.getCallingFunctions(monitor)) {
                if (usable(caller)) {
                    selected.add(caller);
                    roles.putIfAbsent(caller, "caller");
                }
            }
            for (Function callee : seed.getCalledFunctions(monitor)) {
                if (usable(callee)) {
                    selected.add(callee);
                    roles.putIfAbsent(callee, "callee");
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Ghidra decompiler could not open program");
        }

        int completed = 0;
        int failed = 0;
        try (PrintWriter code = new PrintWriter(new BufferedWriter(
                    new FileWriter(new File(outputDirectory, "selected.c"))));
             PrintWriter index = new PrintWriter(new BufferedWriter(
                    new FileWriter(new File(outputDirectory, "functions.tsv"))))) {
            index.println("address\tname\trole\tstatus\tsignature");
            for (Function function : selected) {
                if (monitor.isCancelled()) {
                    break;
                }
                DecompileResults result = decompiler.decompileFunction(
                    function, DECOMPILE_TIMEOUT_SECONDS, monitor);
                String status;
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    status = "ok";
                    code.printf("/* %s %s (%s) */%n", function.getEntryPoint(),
                        function.getName(), roles.get(function));
                    code.println(result.getDecompiledFunction().getC());
                    code.println();
                    completed++;
                } else {
                    status = "failed:" + clean(result.getErrorMessage());
                    failed++;
                }
                index.printf("%s\t%s\t%s\t%s\t%s%n", function.getEntryPoint(),
                    function.getName(), roles.get(function), status,
                    clean(function.getSignature().toString()));
            }
        } finally {
            decompiler.dispose();
        }
        println("Selected " + selected.size() + " functions; exported " + completed +
            "; failed " + failed);
    }
}
