// Export a reproducible, derived inventory without publishing decompiled bodies.
// @category DWARF

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolType;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

public class ExportProgramInventory extends GhidraScript {
    private static String cell(Object value) {
        String text = value == null ? "" : value.toString();
        return "\"" + text.replace("\"", "\"\"").replace("\r", "\\r")
            .replace("\n", "\\n") + "\"";
    }

    private BufferedWriter writer(File directory, String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(directory, name), StandardCharsets.UTF_8));
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected output directory");
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create output directory: " + output);
        }

        exportProgram(output);
        exportFunctions(output);
        exportStrings(output);
        exportImports(output);
        exportCalls(output);
        println("Program inventory written to " + output.getAbsolutePath());
    }

    private void exportProgram(File output) throws Exception {
        try (BufferedWriter out = writer(output, "program.tsv")) {
            out.write("field\tvalue\n");
            out.write("name\t" + cell(currentProgram.getName()) + "\n");
            out.write("language\t" + cell(currentProgram.getLanguageID()) + "\n");
            out.write("compiler\t" + cell(currentProgram.getCompilerSpec().getCompilerSpecID()) + "\n");
            out.write("image_base\t" + cell(currentProgram.getImageBase()) + "\n");
        }
        try (BufferedWriter out = writer(output, "memory-blocks.tsv")) {
            out.write("name\tstart\tend\tsize\tread\twrite\texecute\tinitialized\n");
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                out.write(cell(block.getName()) + "\t" + cell(block.getStart()) + "\t"
                    + cell(block.getEnd()) + "\t" + block.getSize() + "\t"
                    + block.isRead() + "\t" + block.isWrite() + "\t" + block.isExecute()
                    + "\t" + block.isInitialized() + "\n");
            }
        }
    }

    private void exportFunctions(File output) throws Exception {
        try (BufferedWriter out = writer(output, "functions.tsv")) {
            out.write("entry\tname\tnamespace\tsignature\tbody_size\texternal\tthunk\n");
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function function = functions.next();
                out.write(cell(function.getEntryPoint()) + "\t" + cell(function.getName()) + "\t"
                    + cell(function.getParentNamespace().getName(true)) + "\t"
                    + cell(function.getSignature()) + "\t" + function.getBody().getNumAddresses()
                    + "\t" + function.isExternal() + "\t" + function.isThunk() + "\n");
            }
        }
    }

    private void exportStrings(File output) throws Exception {
        try (BufferedWriter out = writer(output, "strings.tsv")) {
            out.write("address\ttype\tvalue\treference_count\treferencing_functions\n");
            for (Data data : currentProgram.getListing().getDefinedData(true)) {
                if (monitor.isCancelled()) break;
                DataType type = data.getDataType();
                if (type == null || !type.getName().toLowerCase().contains("string")) continue;
                Object value = data.getValue();
                if (value == null) continue;
                Set<String> callers = new HashSet<>();
                int count = 0;
                ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(data.getAddress());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    count++;
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                    if (function != null) callers.add(function.getName() + "@" + function.getEntryPoint());
                }
                out.write(cell(data.getAddress()) + "\t" + cell(type.getName()) + "\t" + cell(value)
                    + "\t" + count + "\t" + cell(String.join(";", callers)) + "\n");
            }
        }
    }

    private void exportImports(File output) throws Exception {
        try (BufferedWriter out = writer(output, "imports.tsv")) {
            out.write("address\tname\tnamespace\ttype\n");
            SymbolIterator symbols = currentProgram.getSymbolTable().getExternalSymbols();
            while (symbols.hasNext() && !monitor.isCancelled()) {
                Symbol symbol = symbols.next();
                out.write(cell(symbol.getAddress()) + "\t" + cell(symbol.getName()) + "\t"
                    + cell(symbol.getParentNamespace().getName(true)) + "\t"
                    + cell(symbol.getSymbolType()) + "\n");
            }
        }
    }

    private void exportCalls(File output) throws Exception {
        try (BufferedWriter out = writer(output, "calls.tsv")) {
            out.write("caller_entry\tcaller\tcallsite\tcallee_entry\tcallee\treference_type\n");
            FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
            while (functions.hasNext() && !monitor.isCancelled()) {
                Function caller = functions.next();
                InstructionIterator instructions = currentProgram.getListing()
                    .getInstructions(caller.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    for (Reference ref : instruction.getReferencesFrom()) {
                        if (!ref.getReferenceType().isCall()) continue;
                        Address target = ref.getToAddress();
                        Function callee = currentProgram.getFunctionManager().getFunctionAt(target);
                        if (callee == null) {
                            callee = currentProgram.getFunctionManager().getFunctionContaining(target);
                        }
                        out.write(cell(caller.getEntryPoint()) + "\t" + cell(caller.getName()) + "\t"
                            + cell(instruction.getAddress()) + "\t"
                            + cell(callee == null ? target : callee.getEntryPoint()) + "\t"
                            + cell(callee == null ? "" : callee.getName()) + "\t"
                            + cell(ref.getReferenceType()) + "\n");
                    }
                }
            }
        }
    }
}
