// Decompile functions that reference high-value interoperability strings and
// their direct callers. This avoids spending hours on unrelated library code.
// @category DWARF

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

public class ExportKeywordXrefs extends GhidraScript {
    // Optimized/generated protobuf and third-party functions can keep the
    // decompiler busy for minutes. Triage should skip those outliers and move
    // on; the full exporter remains available for a deliberately deep pass.
    private static final int DECOMPILE_TIMEOUT_SECONDS = 10;
    private static final String[] KEYWORDS = {
        "listen", "bind", "websocket", "ws://", "http://", "rtsp", "jpeg",
        "fitslist", "exposure", "exp_index", "filter", "duo", "dark",
        "motor.bin", "rgb.bin", "ttys", "uart", "signature", "verify",
        "rsa", "sha256", "md5", "update.json", "device.db", "sqlite"
    };

    private static boolean isMatch(String value) {
        String lower = value.toLowerCase(Locale.ROOT);
        for (String keyword : KEYWORDS) {
            if (lower.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private static String clean(String value) {
        String result = value.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ');
        return result.length() <= 240 ? result : result.substring(0, 240) + "...";
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected output directory argument");
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create output directory: " + outputDirectory);
        }

        FunctionManager functionManager = currentProgram.getFunctionManager();
        ReferenceManager referenceManager = currentProgram.getReferenceManager();
        Set<Function> seeds = new LinkedHashSet<>();
        Set<Function> selected = new TreeSet<>(Comparator.comparing(Function::getEntryPoint));

        try (PrintWriter xrefs = new PrintWriter(new BufferedWriter(
                new FileWriter(new File(outputDirectory, "string-xrefs.tsv"))))) {
            xrefs.println("string_address\tfunction_address\tfunction_name\tstring");
            DataIterator dataItems = currentProgram.getListing().getDefinedData(true);
            while (dataItems.hasNext() && !monitor.isCancelled()) {
                Data data = dataItems.next();
                Object value = data.getValue();
                if (!(value instanceof String) || !isMatch((String) value)) {
                    continue;
                }
                ReferenceIterator references = referenceManager.getReferencesTo(data.getAddress());
                while (references.hasNext()) {
                    Reference reference = references.next();
                    Function function = functionManager.getFunctionContaining(reference.getFromAddress());
                    if (function == null || function.isExternal() || function.isThunk()) {
                        continue;
                    }
                    seeds.add(function);
                    selected.add(function);
                    xrefs.printf("%s\t%s\t%s\t%s%n", data.getAddress(), function.getEntryPoint(),
                        function.getName(), clean((String) value));
                }
            }
        }

        // Include one caller level to retain the command/route context around
        // small helper functions that directly touch a matched string.
        for (Function seed : seeds) {
            ReferenceIterator callers = referenceManager.getReferencesTo(seed.getEntryPoint());
            while (callers.hasNext()) {
                Function caller = functionManager.getFunctionContaining(callers.next().getFromAddress());
                if (caller != null && !caller.isExternal() && !caller.isThunk()) {
                    selected.add(caller);
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
                    new FileWriter(new File(outputDirectory, "targeted.c"))));
             PrintWriter index = new PrintWriter(new BufferedWriter(
                    new FileWriter(new File(outputDirectory, "functions.tsv"))))) {
            index.println("address\tname\tstatus\tsignature");
            for (Function function : selected) {
                if (monitor.isCancelled()) {
                    break;
                }
                DecompileResults result = decompiler.decompileFunction(
                    function, DECOMPILE_TIMEOUT_SECONDS, monitor);
                String status;
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    status = "ok";
                    code.printf("/* %s %s */%n", function.getEntryPoint(), function.getName());
                    code.println(result.getDecompiledFunction().getC());
                    code.println();
                    completed++;
                } else {
                    status = "failed:" + result.getErrorMessage().replace('\t', ' ');
                    failed++;
                }
                index.printf("%s\t%s\t%s\t%s%n", function.getEntryPoint(), function.getName(), status,
                    function.getSignature().toString().replace('\t', ' '));
            }
        } finally {
            decompiler.dispose();
        }
        println("Selected " + selected.size() + " functions; exported " + completed +
            "; failed " + failed);
    }
}
