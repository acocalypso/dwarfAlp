// Export every non-external function as C-like Ghidra decompiler output.
// @category DWARF

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class ExportDecompilation extends GhidraScript {
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

        File codeFile = new File(outputDirectory, "decompiled.c");
        File indexFile = new File(outputDirectory, "functions.tsv");
        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Ghidra decompiler could not open program");
        }

        int completed = 0;
        int failed = 0;
        try (PrintWriter code = new PrintWriter(new BufferedWriter(new FileWriter(codeFile)));
             PrintWriter index = new PrintWriter(new BufferedWriter(new FileWriter(indexFile)))) {
            index.println("address\tname\tstatus\tsignature");
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                if (function.isExternal() || function.isThunk()) {
                    continue;
                }
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
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
                index.printf("%s\t%s\t%s\t%s%n",
                    function.getEntryPoint(), function.getName(), status,
                    function.getSignature().toString().replace('\t', ' '));
            }
        } finally {
            decompiler.dispose();
        }
        println("Exported " + completed + " functions; " + failed + " failed");
    }
}
