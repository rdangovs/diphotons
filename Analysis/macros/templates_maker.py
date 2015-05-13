#!/bin/env python

from diphotons.Utils.pyrapp import *
from optparse import OptionParser, make_option
from copy import deepcopy as copy
import os, json
from pprint import pprint

import array

from getpass import getuser

## ----------------------------------------------------------------------------------------------------------------------------------------
## TemplatesApp class
## ----------------------------------------------------------------------------------------------------------------------------------------

## ----------------------------------------------------------------------------------------------------------------------------------------
class TemplatesApp(PlotApp):
    """
    Class to handle template fitting.
    Takes care of preparing templates starting from TTrees.
    Inherith from PyRapp and PlotApp classes.
    """
    
    ## ------------------------------------------------------------------------------------------------------------
    def __init__(self):
        """ 
        Constructor
        """
        super(TemplatesApp,self).__init__(option_groups=[
                ( "Fit definition options. Usually specified through JSON configuration (see templates_maker.json for details)", [
                        make_option("--preselection",dest="preselection",action="store",type="string",
                                    default="",
                                    help="Preselection cuts to be applied."),
                        make_option("--selection",dest="selection",action="store",type="string",
                                    default="",
                                    help="(Di-)Photon selection to be used for analysis. In dataset definition it replaces '%(sel)s'."),                
                        make_option("--aliases",dest="aliases",action="callback",type="string",callback=optpars_utils.ScratchAppend(),
                                    default=[],
                                    help="List of aliases to be defined for each tree. They can be used for selection or variable definition"),
                        make_option("--fits",dest="fits",action="callback",callback=optpars_utils.Load(),type="string",
                                    default={},help="List of templates fits to be performed. Categories, componentd and templates can be specified."),
                        make_option("--mix",dest="mix",action="callback",callback=optpars_utils.Load(),type="string",
                                    default={},help="Configuration for event mixing."),
                        make_option("--dataset-variables",dest="dataset_variables",action="callback",callback=optpars_utils.ScratchAppend(),type="string",
                                    default=[],help="List of variables to be added to dataets."),
                        make_option("--weight-expression",dest="weight_expression",action="store",type="string",
                                    default="",help="Expression used to define datasets weight."),
                        ]
                  ), ("General templates preparation options", [
                        make_option("--compare-templates",dest="compare_templates",action="store_true",default=False,
                                    help="Make templates comparison plots",
                                    ),
                        make_option("--prepare-truth-fit",dest="prepare_truth_fit",action="store_true",default=False,
                                    help="Prepare fit using MC truth templates",
                                    ),
                        make_option("--prepare-nominal-fit",dest="prepare_nominal_fit",action="store_true",default=False,
                                    help="Prepare fit using nominal templates.",
                                    ),
                        make_option("--do-reweight",dest="do_reweight",action="store_true",default=False,
                                    help="Reweight templates to data.",
                                    ),
                        make_option("--reweight-variables",dest="reweight_variables",action="callback",callback=optpars_utils.ScratchAppend(),
                                    default=[],
                                    help="List of variables to be used for reweighting.",
                                    ),
                        make_option("--mix-templates",dest="mix_templates",action="store_true",
                                    default=False,
                                    help="Mix templates.",
                                    ),
                        make_option("--read-ws","-r",dest="read_ws",action="store",type="string",
                                    default=False,
                                    help="List of variables to be used for reweighting.",
                                    ),
                        make_option("--output-file","-o",dest="output_file",action="store",type="string",
                                    default=None,
                                    help="Output file.",
                                    ),
                        make_option("--store-new-only",dest="store_new_only",action="store_true",
                                    default=False,
                                    help="Only store new objects in output file.",
                                    ),
                        make_option("--mc-file",dest="mc_file",action="store",type="string",
                                    default=None,help="default: %default"),
                        ]
                      )
            ])
        
        ## initialize data members
        self.trees_ = {}
        self.datasets_ = {}
        self.aliases_ = {}
        self.variables_ = {}
        self.cache_ = {}
        self.store_ = {}
        self.rename_ = False
        self.store_new_ = False

        ## load ROOT (and libraries)
        global ROOT, style_utils, RooFit
        import ROOT
        from ROOT import RooFit
        import diphotons.Utils.pyrapp.style_utils as style_utils
        ROOT.gSystem.Load("libdiphotonsUtils")
         
        ROOT.gStyle.SetOptStat(111111)
    ## ------------------------------------------------------------------------------------------------------------
    def __call__(self,options,args):
        """ 
        Main method. Called automatically by PyRoot class.
        """
        ## load ROOT style
        self.loadRootStyle()
        from ROOT import RooFit
        ROOT.gStyle.SetOptStat(111111)
        printLevel = ROOT.RooMsgService.instance().globalKillBelow()
        ROOT.RooMsgService.instance().setGlobalKillBelow(RooFit.FATAL)

        if options.store_new_only:
            self.store_new_ = True

        if not options.output_file:
            if options.read_ws: 
                options.output_file = options.read_ws
            else : 
                options.output_file = "templates.root"
        
        if options.read_ws:
            self.readWs(options,args)
        else:
            self.prepareTemplates(options,args)
        
        if options.mix_templates:
            self.mixTemplates(options,args)
            
        if options.compare_templates:
            self.compareTemplates(options,args)
            
        if options.prepare_truth_fit:
            self.prepareTruthFit(options,args)
        
        if options.prepare_nominal_fit:
            self.prepareNominalFit(options,args)


    ## ------------------------------------------------------------------------------------------------------------
    def openOut(self,options):
        if options.read_ws and options.output_file == options.read_ws:
            name    = options.output_file
            tmpname = name.replace(".root","_tmp.root")
            fout    = self.open(tmpname,"recreate")
            self.rename_  = (tmpname,name)
        else:
            fout = self.open(options.output_file,"recreate")
        return fout

    ## ------------------------------------------------------------------------------------------------------------
    def saveWs(self,options,fout=None):            
        if not fout:
            fout = self.openOut(options)
        fout.cd()
        cfg = { "fits"   : options.fits,
                "stored" : self.store_.keys() 
                }
        
        ROOT.TObjString( json.dumps( cfg,indent=4,sort_keys=True) ).Write("cfg")
        for key,val in self.store_.iteritems():
            val.CloneTree().Write(key,ROOT.TObject.kWriteDelete)
        self.workspace_.Write()
        fout.Close()
        
        if self.rename_:
            os.rename( *self.rename_ )

    ## ------------------------------------------------------------------------------------------------------------
    def readWs(self,options,args):
        print
        print "--------------------------------------------------------------------------------------------------------------------------"
        print "Reading back workspace from %s " % options.read_ws
        print 
        fin = self.open(options.read_ws)
        cfg = json.loads( str(fin.Get("cfg").GetString()) )
        options.fits = cfg["fits"]
        self.workspace_ = fin.Get("wtemplates")
        self.workspace_.rooImport = getattr(self.workspace_,"import")
        for name in cfg["stored"]:
            self.store_[name]=fin.Get(name)
                
        print "Fits :"
        print "---------------------------------------------------------"
        for key,val in options.fits.iteritems():
            print "- %s \n  ndim : %d \n  components : %s" % ( key, val["ndim"], ",".join(val["components"]) )
            print
        
        print "TTrees :"
        print "---------------------------------------------------------"
        for key,val in self.store_.iteritems():
            print key.ljust(30), ":", ("%d" % val.GetEntries()).rjust(8)
        print
        
        print "Datasets :"
        print "---------------------------------------------------------"
        alldata = self.workspace_.allData()
        for dset in alldata:
            name = dset.GetName()
            print name.ljust(30), ":", ("%d" % dset.sumEntries()).rjust(8)

        print    
        print "--------------------------------------------------------------------------------------------------------------------------"

        if self.store_new_:
            self.store_input_ = self.store_
            self.store_ = {}
            
            self.workspace_input_ = self.workspace_
            self.workspace_ = ROOT.RooWorkspace("wtemplates","wtemplates")
            self.workspace_.rooImport = getattr(self.workspace_,"import")
            

    ## ------------------------------------------------------------------------------------------------------------
   #MQ compare truth templates with rcone and sideband templates
    def compareTemplates(self,options,args):
        print "Compare truth templates with rcone and sideband templates"
        for name, comparison in options.comparisons.iteritems():
            if name.startswith("_"): continue
            print "Comparison %s" % name
            fitname=comparison["fit"]
            fit=options.fits[fitname]
            components=comparison.get("components",fit["components"])
            for comp in components:
                if type(comp) == str or type(comp)==unicode:
                    compname = comp
                    templatesls = comparison["templates"]
                else:
                    compname, templatesls = comp

                for cat in fit["categories"]:
                    print "mctruth_%s_%s_%s" % (compname,fitname,cat)
                    truth = self.rooData("mctruth_%s_%s_%s" % (compname,fitname,cat) )
                    print truth.GetName()
                    templates = []
                    for template,mapping in templatesls.iteritems():
                        if "mix" in template:
                             mixname = template.split(":")[-1]
                             templatename= "template_mix_%s_%s_%s" % (compname,mixname,mapping.get(cat,cat))
                        else:
                             templatename= "template_%s_%s_%s" % (compname,template,mapping.get(cat,cat))
                        print templatename
                        tempdata = self.rooData(templatename)
                        templates.append(tempdata)
                    self.keep(truth)
                    self.keep(templates)
                    
                    for idim in range(fit["ndim"]):
                        print "templateNdim%dDim%d" % ( fit["ndim"],idim)
                        title = "compiso_%s_%s_%s_templateNdim%dDim%d" % (fitname,compname,cat,fit["ndim"],idim)
                        canv_allmlog = ROOT.TCanvas("%slog" %(title),"%slog"%title)
                        pad2=ROOT.TPad("pad2", "pad2", 0, 0.0, 1, 0.15)
                        pad1 = ROOT.TPad("pad1", "pad1", 0., 0.0, 1., 1.0)
                        pad1.SetBottomMargin(0)
                        pad1.SetLogy()
                        pad1.Draw()
                        pad1.cd()
                        leg = ROOT.TLegend(0.5,0.6,0.9,0.9)
                        leg.SetFillColor(ROOT.kWhite) 
                    #self.workspace_.Print()
                        isovar=self.workspace_.var("templateNdim%dDim%d" % ( fit["ndim"],idim))
                        template_binning = array.array('d',comparison.get("template_binning",fit["template_binning"]))
                        templatebins=ROOT.RooBinning(len(template_binning)-1,template_binning,"templatebins" )
                        isovar.setBinning(templatebins)
                        print isovar
                        isoframe=isovar.frame()
                        isoframe.SetTitle("%slog" % title)
                        truth.plotOn(isoframe,RooFit.Rescale(1./truth.sumEntries()),RooFit.Binning(templatebins),RooFit.MarkerStyle(20),RooFit.MarkerColor(ROOT.kRed+1),RooFit.LineColor(ROOT.kRed+1),RooFit.Name(truth.GetTitle()))
                        i=0
                        for temp in templates:
                            i+=2
                            temp.plotOn(isoframe,RooFit.Rescale(1./temp.sumEntries()),RooFit.Binning(templatebins),RooFit.MarkerStyle(20),RooFit.MarkerColor(ROOT.kGreen+i),RooFit.LineColor(ROOT.kGreen+i),RooFit.Name(temp.GetTitle()))
                        isoframe.Draw()
                        leg.AddEntry(truth.GetTitle(),truth.GetTitle(),"l")  
                        for temp in templates:
                          leg.AddEntry(temp.GetTitle(),temp.GetTitle(),"l");
                        leg.Draw()
                        isoframe.SetAxisRange(1e-3,20,"Y")
                        pad1.Update()
                        isoarg=ROOT.RooArgList("isoarg")
                        isoarg.add(isovar)
                        truthHisto=ROOT.TH1F("%sHisto" % truth.GetTitle(),"%sHisto" % truth.GetTitle(),len(template_binning)-1,template_binning)
                        truth.fillHistogram(truthHisto,isoarg)
                        truthHisto.GetXaxis().SetLimits(min(template_binning),max(template_binning))
                        truthHisto.GetYaxis().SetLimits(0.1,10.)
                        j=0
                        pad2.SetBottomMargin(0.3)
                        pad2.SetTicks(0,2)
                        pad2.SetTicky()
                        pad2.Draw()
                        pad2.cd()
                        pad2.Update()
                        ROOT.gStyle.SetOptStat(111111)
                        ROOT.gStyle.SetOptTitle(0)
                        for temp in templates:
                            j+=2
                            tempHisto=ROOT.TH1F("%sHisto" % temp.GetTitle(),"%sHisto" % temp.GetTitle(),len(template_binning)-1,template_binning)
                            temp.fillHistogram(tempHisto,isoarg)
                            tempHisto.Divide(truthHisto)
                            tempHisto.SetLineColor(ROOT.kGreen+j)
                            tempHisto.SetMarkerColor(ROOT.kGreen+j)
                            if j==2:
                                tempHisto.Draw()
                            else:
                                tempHisto.Draw("SAME")
                         #   self.keep(tempHisto)
                        pad2.Update()
                        self.keep( [canv_allmlog] )
                        self.autosave(True)


## ------------------------------------------------------------------------------------------------------------
    def prepareTruthFit(self,options,args):
        self.saveWs(options)

    ## ------------------------------------------------------------------------------------------------------------
    def prepareNominalFit(self,options,args):
        self.saveWs(options)
    
    ## ------------------------------------------------------------------------------------------------------------
    def prepareTemplates(self,options,args):
        
        fout = self.openOut(options)
        self.workspace_ = ROOT.RooWorkspace("wtemplates","wtemplates")
        tmp = fout

        ## read input trees
        self.datasets_["data"] = self.openDataset(None,options.data_file,options.infile,options.data)
        self.datasets_["mc"]   = self.openDataset(None,options.mc_file,options.infile,options.mc)
        self.datasets_["templates"]   = self.openDataset(None,options.data_file,options.infile,options.templates)
        # used by parent class PlotApp to read in objects
        self.template_ = options.treeName
        
        self.groups = options.groups
        if options.groups:
            self.categories_ = options.groups.keys()
        else:
            self.categories_ = options.categories
            
        ## create output workspace
        self.workspace_.rooImport = getattr(self.workspace_,"import")

        ## read and store list of aliases. will be defined later in all trees
        for var in options.aliases:
            self.getVar(var)
        
        ## define list of variables for the dataset
        varlist = ROOT.RooArgList()
        weight  = self.getVar(options.weight_expression)[0]
        for var in options.dataset_variables+[weight]:
            name, binning = self.getVar(var)
            rooVar = self.buildRooVar(name,binning)
            varlist.add(rooVar)
            
        ## loop over configured fits
        for name, fit in options.fits.iteritems():
            print
            print "--------------------------------------------------------------------------------------------------------------------------"
            print "Preparing fit %s" % name
            print 
            
            ndim            = fit["ndim"]
            bins            = fit["bins"]
            components      = fit["components"]
            categories      = fit["categories"]
            truth_selection = fit["truth_selection"]
            template_binning = array.array('d',fit["template_binning"])
            templates       = fit["templates"]
            storeTrees      = fit.get("store_trees",False)
            selection       = fit.get("selection",options.selection)
            preselection    = fit.get("preselection",options.preselection)
            
            variables       = fit.get("dataset_variables",[])

            fulllist = varlist.Clone()
            for var in variables:
                vname, binning = self.getVar(var)
                rooVar = self.buildRooVar(vname,binning)
                fulllist.add(rooVar)
            
            for dim in range(ndim):
                dimVar = self.buildRooVar("templateNdim%dDim%d" % (ndim,dim),template_binning)
                fulllist.add( dimVar )
            print "Will put the following variables in the dataset : "
            fulllist.Print()
            
            print "Number of dimensions : %d" % ndim
            print "Components           : %s" % ",".join(components)
            print 
            
            tmp.cd()
            
            ## prepare data
            dataTrees = self.prepareTrees("data",selection,options.verbose,"Data trees")
            self.buildRooDataSet(dataTrees,"data",name,fit,categories,fulllist,weight,preselection,storeTrees)
            
            ## prepare mc
            mcTrees =  self.prepareTrees("mc",selection,options.verbose,"MC trees")
            self.buildRooDataSet(mcTrees,"mc",name,fit,categories,fulllist,weight,preselection,storeTrees)
            
            ## prepare truth templates
            for truth,sel in truth_selection.iteritems():
                cut = ROOT.TCut(preselection)
                cut *= ROOT.TCut(sel)
                legs = [""]
                if "legs" in fit:
                    legs = fit["legs"]
                self.buildRooDataSet(mcTrees,"mctruth_%s" % truth,name,fit,categories,fulllist,weight,cut.GetTitle(),storeTrees)
            
                        
            print
            ## sanity check
            for cat in categories.keys():
                catCounts = {}
                catCounts["tot"] = self.rooData("mc_%s_%s" % (name,cat) ).sumEntries()
                
                breakDown = 0.
                for truth in truth_selection.keys():
                    count = self.rooData("mctruth_%s_%s_%s" % (truth,name,cat) ).sumEntries()
                    breakDown += count
                    catCounts[truth] = count
                print cat, " ".join( "%s : %1.4g" % (key,val) for key,val in catCounts.iteritems() ),
                if breakDown != catCounts["tot"]:
                    print "\n   Warning : total MC counts don't match sum of truths. Difference: ", catCounts["tot"]-breakDown
                else:
                    print
                
            ## prepare templates
            print 
            for component,cfg in fit["templates"].iteritems():
                dataset = cfg.get("dataset","templates")
                trees = self.prepareTrees(dataset,cfg["sel"],options.verbose,"Templates selection for %s" % component)
                cats = {}
                presel = cfg.get("presel",preselection)
                for cat,fill in cfg["fill_categories"].iteritems():
                    config = { "src" : categories[cat]["src"],
                               "fill": fill
                               }
                    cats[cat] = config
                self.buildRooDataSet(trees,"template_%s" % component,name,fit,cats,fulllist,weight,presel,storeTrees)
                for cat in categories.keys():
                    print "template %s - %s" % (component,cat), self.rooData("template_%s_%s_%s" % (component,name,cat) ).sumEntries()
            print 
            print "--------------------------------------------------------------------------------------------------------------------------"
            print 

        if options.mix_templates:
            self.doMixTemplates(options,args)

        self.saveWs(options,fout)
    
    ## ------------------------------------------------------------------------------------------------------------
    def mixTemplates(self,options,args):
        fout = self.openOut(options)
        fout.Print()
        fout.cd()
        self.doMixTemplates(options,args)
        self.saveWs(options,fout)
    
    ## ------------------------------------------------------------------------------------------------------------
    def doMixTemplates(self,options,args):
        
        for name, mix in options.mix.iteritems():
            print
            print "--------------------------------------------------------------------------------------------------------------------------"
            print "Mixing templates %s" % name
            print 

            targetName      = mix["target"]
            targetFit       = options.fits[targetName]
            ndim            = targetFit["ndim"]
            ## categories      = target["categories"]
            
            ptLeadMin       = mix["ptLeadMin"]
            ptSubleadMin    = mix["ptSubleadMin"]
            massMin         = mix["massMin"]
            mixType         = mix.get("type","simple") 

            pt              = mix["pt"]
            eta             = mix["eta"]
            phi             = mix["phi"]
            energy          = mix["energy"]
            replace         = mix["replace"]
            fill_categories = mix["fill_categories"]
            
            if mixType == "simple":
                matchVars = ROOT.RooArgList() # FIXME
                for var,thr in mix["match"].iteritems():
                    var = self.buildRooVar(var,[])
                    var.setVal(thr)
                    matchVars.add(var)

            elif mixType == "kdtree":
                pass
            else:
                sys.exit(-1,"Uknown event mixing type %s" % mixType)
  
            if ndim != 2:
                sys.exit(-1,"can only do event mixing with two objects")

            sources = {}
            print "Source templates: "            
            for comp,source in mix["sources"].iteritems():
                print comp, ":", " ".join(source)
                sources[comp] = [ s.split(":") for s in source ]
            print

            for cat, fill in fill_categories.iteritems():
                print
                print "Filling category :", cat
                for comp,source in sources.iteritems():
                    legs = []
                    legnams = []
                    print
                    print "Component :", comp
                    for leg,src in zip(fill["legs"],source):
                        sname,scomp = src
                        legname = "template_%s_%s_%s" % (scomp,sname,leg)
                        legnams.append( legname )
                        dset = self.rooData(legname,False)
                        legs.append( (self.treeData(legname),ROOT.RooArgList(self.dsetVars(legname)) ) )
                    if len(legs) != ndim:
                        sys.exit(-1,"number of legs does not match number of dimensions for dataset mixing")
                    rndswap     = fill.get("rndswap",False)
                    
                    print "legs  :", " ".join(legnams)
                    print "type  :", mixType
                    
                    (tree1, vars1), (tree2, vars2)  = legs
                    mixer = ROOT.DataSetMixer( "template_mix_%s_%s_%s" % ( comp, name, cat),"template_mix_%s_%s_%s" % ( comp, name, cat),
                                               vars1, vars2, replace, replace,
                                               ptLeadMin, ptSubleadMin, massMin,
                                               "weight", "weight", True,                                               
                                               )
                    
                    if mixType == "simple":
                        maxEvents   = fill.get("maxEvents",-1)
                        matchEffMap = fill.get("matchEff",{})
                        matchEff    = matchEffMap.get(comp,1.)
                        print "maxEvents :", maxEvents, "rndswap :", rndswap, "mathcEffMap"
                        mixer.fillFromTree(tree1,tree2,pt,eta,phi,energy,pt,eta,phi,energy,matchVars,rndswap,maxEvents,matchEff)
                        
                    elif mixType == "kdtree":
                        targetCat       = fill.get("targetCat",cat)
                        nNeigh          = fill.get("nNeigh",10)
                        useCdfDistance  = fill.get("useCdfDistance",False)
                        targetWeight    = fill.get("targetWeight","weight")
                        dataname        = "data_%s_%s" % (targetName,targetCat)                        
                        target          = self.treeData(dataname)
                    

                        matchVars1   = ROOT.RooArgList()
                        matchVars2   = ROOT.RooArgList()
                        targetMatch1 = ROOT.RooArgList()
                        targetMatch2 = ROOT.RooArgList()
                        
                        for var in fill["match1"]:
                            var = self.buildRooVar(var,[])
                            matchVars1.add(var)
                        for var in fill["match2"]:
                            var = self.buildRooVar(var,[])
                            matchVars2.add(var)
                        for var in fill["target1"]:
                            var = self.buildRooVar(var,[])
                            targetMatch1.add(var)
                        for var in fill["target2"]:
                            var = self.buildRooVar(var,[])
                            targetMatch2.add(var)
                            
                        print "target :", dataname
                        print "rndswap :", rndswap, "useCdfDistance :", useCdfDistance, "nNeigh :", nNeigh
                        mixer.fillLikeTarget(target,targetMatch1,targetMatch1,targetWeight,tree1,tree2,
                                             pt,eta,phi,energy,pt,eta,phi,energy,
                                             matchVars1,matchVars2,rndswap,nNeigh,useCdfDistance)
                    
                    dataset = mixer.get()
                    self.workspace_.rooImport(dataset,ROOT.RooFit.RecycleConflictNodes())
                    tree = mixer.getTree()
                    self.store_[tree.GetName()] = tree

            print 
            print "--------------------------------------------------------------------------------------------------------------------------"
            print 


    ## ------------------------------------------------------------------------------------------------------------
    def setAliases(self,tree):
        """ Define all aliases in tees
        """
        for var,vdef in self.aliases_.iteritems():
            tree.SetAlias(var,vdef)
    
    ## ------------------------------------------------------------------------------------------------------------
    def rooData(self,name,autofill=True):
        if name in self.cache_:
            return self.cache_[name]        
        dataset = self.workspace_.data(name)
        if not dataset and self.store_new_:
            dataset = self.workspace_input_.data(name)
            
        if autofill and dataset.sumEntries() == 0. and "tree_%s" % name in self.store_:
            tree = self.store_["tree_%s" % name]
            dataset = dataset.emptyClone()
            self.cache_[name] = dataset
            filler = ROOT.DataSetFiller(dataset)
            filler.fillFromTree(tree,"weight",True)
        return dataset

    ## ------------------------------------------------------------------------------------------------------------
    def treeData(self,name):
        if "tree_%s" % name in self.store_:
            return self.store_["tree_%s" % name]
        elif self.store_new_ and "tree_%s" % name in self.store_input_:
            return self.store_input_["tree_%s" % name]
        return None
        
    ## ------------------------------------------------------------------------------------------------------------
    def dsetVars(self,name):
        st = self.workspace_.set("variables_%s" %name)
        if not st and self.store_new_:
            st = self.workspace_input_.set("variables_%s" %name)
        return st

    ## ------------------------------------------------------------------------------------------------------------
    def getVar(self,var):
        """ 
        Parse variable definition
        General form:
        'var := expression [binning]'
        ':= expression' can be omitted if the variable already exists in trees.
        '[binning]' is also optional and can be specified as [nbins,min,max] or list of boundaires.
        """
        if "[" in var:
            name,binning = var.rstrip("-").rstrip("]").rsplit("[",1)
            
            if "," in binning:
                binning = binning.split(",")
            else:
                binning = binning.split(":")
            if len(binning) == 3:
                nbins = int(binning[0])
                xmin = float(binning[1])
                xmax = float(binning[2])
                step = ( xmax - xmin ) / float(nbins)
                xbins = array.array('d',[xmin+step*float(ib) for ib in range(nbins+1)])
            else:
                xbins = array.array('d',[float(b) for b in binning])
        else:
            name,xbins = var.rstrip("-"),[]

        if ":=" in name:
            name,vdef = [ t.lstrip(" ").rstrip(" ").lstrip("\t").rstrip("\t") for t in name.split(":=",1) ]
            self.aliases_[name] = vdef
            
        name = name.lstrip(" ").rstrip(" ").lstrip("\t").rstrip("\t")
        if len(xbins) == 0 and name in self.variables_:
            xbins = self.variables_[name]
        else:
            self.variables_[name] = xbins
        return name,xbins

    ## ------------------------------------------------------------------------------------------------------------
    def buildRooVar(self,name,binning):
        if name in self.aliases_:
            title = self.aliases_[name]
        else:
            title = name
        rooVar = ROOT.RooRealVar(name,title,0.)
        if len(binning) > 0:
            rooVar.setMin(binning[0])
            rooVar.setMax(binning[-1])
            rooVar.setVal(0.5*(binning[0]+binning[-1]))
            rooVar.setBinning(ROOT.RooBinning(len(binning)-1,binning))
        self.workspace_.rooImport(rooVar,ROOT.RooFit.RecycleConflictNodes())
        self.keep(rooVar) ## make sure the variable is not destroyed by the garbage collector
        return rooVar

    ## ------------------------------------------------------------------------------------------------------------
    def buildRooDataSet(self,trees,name,fitname,fit,categories,fulllist,weight,preselection,storeTrees):
        """ Build per-category RooDataSet starting from trees
        """
        # define loop over legs
        legs = [""]
        redef = []        
        if "legs" in fit:
            legs = fit["legs"]
            redef = [ fulllist[ivar].GetTitle()  for ivar in range(fulllist.getSize() ) ]

        ## fill datasets
        for catname,cfg in categories.iteritems():
            filler = ROOT.DataSetFiller( "%s_%s_%s" % (name,fitname,catname), "%s_%s_%s" % (name,fitname,catname), fulllist, weight, storeTrees )
            
            ## source category
            src = trees[cfg["src"]]
            
            ## filling directives
            fill  = cfg["fill"]

            ## loop over directives 
            for cut,variables in fill.iteritems():
                # assume template vars are at the end
                firstVar = fulllist.getSize()-len(variables)
                ## loop over all legs
                for leg in legs:
                    ## adapt the definition of all variables
                    for ired, red in enumerate(redef):
                        filler.vars()[ired].SetTitle(red % {"leg" : leg})
                    ## adapt the definition of the template variables
                    for ivar,var in enumerate(variables):
                        filler.vars()[firstVar+ivar].SetTitle(var % {"leg" : leg})
                
                    ## compute weight as preselection*cut*weight
                    wei  = ROOT.TCut(preselection)
                    wei *= ROOT.TCut(cut)
                    wei *= ROOT.TCut(weight)
                    
                    ## fill dataset from source trees
                    for tree in src:
                        twei = wei.GetTitle() % {"leg" : leg}
                        ## this will actually discard all events with weight 0 
                        ##   or outside of the range of any variable in fulllist
                        filler.fillFromTree(tree,twei)
            
            # restore variables definition
            for ired, red in enumerate(redef):
                fulllist[ired].SetTitle(red)
                
            ## and we are done
            dataset = filler.get()
            self.workspace_.rooImport(dataset,ROOT.RooFit.RecycleConflictNodes())

            variables = ROOT.RooArgSet(filler.vars())
            self.workspace_.defineSet("variables_%s" % dataset.GetName(),variables)
            
            if storeTrees:
                tree = filler.getTree()
                self.store_[tree.GetName()] = tree
                
            ## dataset.Print()

    ## ------------------------------------------------------------------------------------------------------------
    def prepareTrees(self,name,selection,doPrint=False,printHeader=""): 
        """ Read trees from input file(s) and set all aliases 
        """ 
        if doPrint:    
            print "%s :" % printHeader
        
        ## read trees for given selection
        allTrees = self.getTreesForSelection(name,selection)
        for cat,trees in allTrees.iteritems():
            treePaths = []
            ## set aliases
            for t in trees:
                self.setAliases(t)
                treePaths.append( "%s/%s" % (os.path.relpath(t.GetDirectory().GetPath()), t.GetName()) )
            if doPrint:
                print " %s : \n  %s" % (cat, "\n  ".join(treePaths) ) 

        if doPrint:    
            print 
           
        return allTrees

    ## ------------------------------------------------------------------------------------------------------------
    def getTreesForSelection(self,dataset,selection):
        """ Load trees used for datasets definition.
        """ 
        ret = {}
        
        ## keep track of already loaded datasets
        key = "%s:%s" % ( dataset, selection ) 
        if not key in self.trees_:
            infile,samplesTmpl = self.datasets_[dataset]
            
            ## replace %(sel)s keyword with choosen selection
            replacements = { "sel" : selection }
            samples = [ s % replacements for s in samplesTmpl ]
            
            ## initialize list of trees: one entry per category
            self.trees_[key] = {}
            
            ## loop over categories and read in trees
            for cat in self.categories_:
                if type(cat) == int: 
                    catname = "cat%d" % cat
                else:
                    catname = cat
                    group = None
                if self.groups:
                    group = self.groups[cat]
                
                # call PlotApp.readObjects to read trees
                self.trees_[key][catname] = self.readObjects(infile,"",samples=samples,cat=catname,group=group)
                
        ## done
        return self.trees_[key]

        
    ## ------------------------------------------------------------------------------------------------------------
    ## End of class definition
    ## ------------------------------------------------------------------------------------------------------------


# -----------------------------------------------------------------------------------------------------------
# actual main
if __name__ == "__main__":
    app = TemplatesApp()
    app.run()