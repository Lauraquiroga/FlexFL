import BoostNSift.BoostN;
import configuration.ConfigurationParameters;
import corpusGenerator.MainCorpusGenerator;
import corpusGenerator.PathsOfSourceFiles;
import corpusPreprocessor.MainCorpusPreprocessor;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVPrinter;
import org.apache.log4j.Logger;
import org.apache.log4j.PropertyConfigurator;
import org.apache.lucene.queryparser.classic.ParseException;
import utilities.ExecuteCommandLine;

import java.io.*;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class Main {
    static String[] paths = null;
    protected static Logger logger = Logger.getLogger(Main.class);

    public static void checkoutDefects4jDefect(String project, String defectid) throws Exception{

        File chkout_dir= new File(ConfigurationParameters.bugCheckoutDirectory);
        if (!chkout_dir.exists())
            chkout_dir.mkdir();

        String command1 = "rm -rf " + ConfigurationParameters.getDefectRepoPath(project, defectid);
        logger.info("running cmd: " + command1);
        ExecuteCommandLine.executeCommand(command1);

        String command2 = ConfigurationParameters.defects4JHome + "framework/bin/defects4j checkout -p " + project + " -v " + defectid + "b -w "
                + ConfigurationParameters.getDefectRepoPath(project, defectid);
        logger.info("running cmd: " + command2);
        ExecuteCommandLine.executeCommand(command2);

        // 为什么需要compile？
        logger.info(ExecuteCommandLine.executeCommandAndGetOutput("which java"));
        String command3 = ConfigurationParameters.defects4JHome + "framework/bin/defects4j compile "
                + "-w " + ConfigurationParameters.getDefectRepoPath(project, defectid);
        logger.info("running cmd: " + command3);
        logger.info(ExecuteCommandLine.executeCommandAndGetOutput(command3));
    }

    /*  for each defect, get all the Java files from the source directory, preprocess code to extract tokens and write to docs
     *
     */
    public static void extractJavaFilesAndCreateDocs(String defect) throws Exception {

        logger.info("processing defect: " + defect);

        File src_doc_dir= new File(ConfigurationParameters.sourceDocumentsDirectory);
        if (!src_doc_dir.exists())
            src_doc_dir.mkdirs();

        String doc_dir = ConfigurationParameters.sourceDocumentsDirectory + "/" + defect;
        File theDir = new File(doc_dir);
        logger.info("storing file docs at " + doc_dir);
        // if the directory does not exist, create it
        if (!theDir.exists()) {
            logger.info("creating directory: " + theDir.getName());
            boolean result = false;
            try {
                theDir.mkdir();
                result = true;
            } catch (SecurityException se) {
                logger.error("cannot create directory at " + theDir.getName());
            }
            if (result) {
                logger.info("created directory");
            }
        }

        String project = defect.split("-")[0];
        String defectid = defect.split("-")[1];
        logger.info("checkout buggy version of program");
        checkoutDefects4jDefect(project, defectid);

        String command5 = ConfigurationParameters.defects4JHome + "framework/bin/defects4j export -p dir.src.classes "
                + "-w " + ConfigurationParameters.getDefectRepoPath(project, defectid);
        logger.info("running cmd: " + command5);
        String[] output = ExecuteCommandLine.executeCommandAndGetOutput(command5).split("\n");
        String source_folder_name = output[output.length-1].trim();
        String source_folder_path = ConfigurationParameters.getDefectRepoPath(project, defectid) + "/" + source_folder_name;
        logger.info("source folder name: " + source_folder_name);
        logger.info("source folder path: " + source_folder_path);

        String source_folder_file = ConfigurationParameters.getDocDir(defect) + "source_folder.txt";
        try (FileWriter writer = new FileWriter(source_folder_file)) {
            writer.write(source_folder_name);
            writer.flush();
        }

        File sourcepath = new File(source_folder_path);
        if (!sourcepath.exists()){
            logger.error("source path DNE!: " + sourcepath);
            return;
        }
        if (!sourcepath.isDirectory()){
            logger.error("source folder DNE!: " + source_folder_path);
            return;
        }

        // create SourcePaths.txt
        String source_list_file = ConfigurationParameters.getDefectRepoPath(project, defectid) + "/" + "SourcePaths.txt";
        String[] args = {source_list_file, source_folder_path};
        PathsOfSourceFiles.main(args);

        // generate corpus
        String granularity = "-methodLevelGranularity";
        String outputFolder = ConfigurationParameters.getDocDir(project, defectid);
        String filePrefix = project + "-" + defectid;
        String[] genArgs = {granularity, source_list_file, outputFolder, filePrefix};
        MainCorpusGenerator.main(genArgs);
    }

    public static void preprocessCorpusAndDocs(String defect) throws Exception {
        // corpus
        String inputFile = ConfigurationParameters.getDocDir(defect) + ConfigurationParameters.getFilePrefix(defect) + ".corpusRawMethodLevelGranularity";
        String[] args = {inputFile, ConfigurationParameters.getDocDir(defect)};
        logger.info("Preprocessor parameters: " + Arrays.toString(args));
        MainCorpusPreprocessor.main(args);

        // description
        inputFile = ConfigurationParameters.flattenedBRDir + "/" + ConfigurationParameters.getFilePrefix(defect) + "_Desc.csv";
        String[] descArgs = {inputFile, ConfigurationParameters.getDocDir(defect)};
        logger.info("Preprocessor parameters: " + Arrays.toString(descArgs));
        MainCorpusPreprocessor.main(descArgs);

        // title
        inputFile = ConfigurationParameters.flattenedBRDir + "/" + ConfigurationParameters.getFilePrefix(defect) + "_Titles.csv";
        String[] titleArgs = {inputFile, ConfigurationParameters.getDocDir(defect)};
        logger.info("Preprocessor parameters: " + Arrays.toString(titleArgs));
        MainCorpusPreprocessor.main(titleArgs);

        // comment: should be empty
        inputFile = ConfigurationParameters.flattenedBRDir + "/" + ConfigurationParameters.getFilePrefix(defect) + "_Comm.csv";
        String[] commArgs = {inputFile, ConfigurationParameters.getDocDir(defect)};
        logger.info("Preprocessor parameters: " + Arrays.toString(commArgs));
        MainCorpusPreprocessor.main(commArgs);
    }

    public static void callBoostN(String defect) throws IOException, ParseException {
        String[] args = {ConfigurationParameters.getDocDir(defect), ConfigurationParameters.getFilePrefix(defect)};
        BoostN.main(args);
    }

    public static void reformatResult(String defect) throws IOException {
        String mappingFilePath = ConfigurationParameters.getDocDir(defect) + ConfigurationParameters.getFilePrefix(defect) + ".corpusMappingMethodLevelGranularity";
        List<String> methods = Files.readAllLines(Paths.get(mappingFilePath));
        String outFile = ConfigurationParameters.getDocDir(defect) + "method-susps.csv";

        String resultFilePath = ConfigurationParameters.getDocDir(defect) + "Results.csv";
        // The result should only contain one line
        String result = Files.readAllLines(Paths.get(resultFilePath)).get(0).trim();
        String[] items = result.split(",");

        List<String[]> scores = new ArrayList<>();
        for (int i=0;i<items.length;i=i+2){
            String methodSig = methods.get(Integer.parseInt(items[i]));
            String[] sigItems = methodSig.split("\\.");
            String endLine = sigItems[sigItems.length-1];
            String startLine = sigItems[sigItems.length-2];
            String sig = sigItems[sigItems.length-3];
            String file = String.join(".", Arrays.asList(sigItems).subList(0, sigItems.length-3));
            String score = items[i+1];
            scores.add(new String[]{file, sig, startLine, endLine, score});
        }

        String[] headers = {"File", "Signature", "StartLine", "EndLine", "Suspiciousness"};
        CSVFormat csvFormat = CSVFormat.DEFAULT.builder()
                .setHeader(headers)
                .build();

        try (FileWriter writer = new FileWriter(outFile);
             final CSVPrinter printer = new CSVPrinter(writer, csvFormat)){
                scores.forEach( methodItem -> {
                    try {
                        printer.printRecord(methodItem[0], methodItem[1], methodItem[2], methodItem[3], methodItem[4]);
                    } catch (IOException e) {
                        e.printStackTrace();
                    }
                });
        }

    }

    public static void processOneDefect(String defect) throws Exception {
        // 对于每个bug，check out相应的仓库，提取其中的文件，构建相应的corpus
        logger.info("Processing Defect: " + defect);
        logger.info("Extracting Java source files and creating docs");
        extractJavaFilesAndCreateDocs(defect);

        logger.info("Preprocess Corpus and Docs");
        preprocessCorpusAndDocs(defect);

        logger.info("Call BoostN to obtain the result");
        callBoostN(defect);

        logger.info("Reformat the results of BoostN");
        reformatResult(defect);
    }

    public static void main(String[] args) throws Exception {
        String granularity = "-methodLevelGranularity";
        String filePrefix = args[0];
        String outputFolder = "../methods_buggy_Defects4j/";
        String file_list = "../file_lists_buggy/"+filePrefix+".txt";
        String[] genArgs = {granularity, file_list, outputFolder, filePrefix};
        MainCorpusGenerator.main(genArgs);

        //Since we are given the ground truth, we can avoid generating the _fixed_ folders

        // outputFolder = "../methods_fixed_Defects4j/";
        // file_list = "../file_lists_fixed/"+filePrefix+".txt";
        // String[] genArgs_ = {granularity, file_list, outputFolder, filePrefix};
        // MainCorpusGenerator.main(genArgs_);




//        BasicConfigurator.configure();
        // Properties props = new Properties();
        // String confFile = Objects.requireNonNull(Main.class.getClassLoader().getResource("log4j.properties")).getFile();
        // props.load(Files.newInputStream(Paths.get(confFile)));
        // PropertyConfigurator.configure(props);
        // ConfigurationParameters.setParametersFromSettingsFile();
        // paths = ConfigurationParameters.CommitDBPaths.split(",");

        // String defectinfo = args[0];

        // if (defectinfo.contentEquals("all")) {
        //     logger.info("Fetching bug reports and creating XML queries");

        //     List<String> allDefects = Files.readAllLines(Paths.get(ConfigurationParameters.bugListFile));
        //     logger.info("total #defects:" + allDefects.size());
        //     for (String defect: allDefects) {
        //         String resultFile = ConfigurationParameters.getDocDir(defect) + "Results.csv";
        //         if ((new File(resultFile)).exists()) {
        //             logger.warn(defect + " have been processed. Skip.");
        //             continue;
        //         }
        //         processOneDefect(defect);
        //     }
        // } else {
        //     processOneDefect(defectinfo);
        // }
    }
}
