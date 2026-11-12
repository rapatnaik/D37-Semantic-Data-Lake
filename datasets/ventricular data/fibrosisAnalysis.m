%log
%.....
% 7 Oct: added processing of vimentin and asma images to include dapi
% signal in their volume fraction calculation
% 29 Oct: changed threshold calculation by using the separate ROI defined
% for mod (for some images) for calculating sd also
%4 Nov  added masks for fibrotic areas not well detected by thresholding
%29 Nov fibrotic mask and bounding box size was off by 1 pixel, bounding
%box adjusted to match

%%
addpath Scripts

%f_sd =  1 for wga, 2.5 for vim , and 3 for asma
images={
    {'190930_1_overview','group','HF','etiology','IC','orientation','o','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191007_1_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191007_2_overview','group','HF','etiology','NIC','orientation','o','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191017_1_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191017_5_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191101_1_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191108_1_overview','group','HF','etiology','IC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191107_2_overview','group','HF','etiology','NIC','orientation','o','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191210_4_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','2'}
    {'191211_3_overview','group','HF','etiology','IC','orientation','o','channel_wga','3','channel_asma','4','channel_vim','2'}
    {'200318_1_overview','group','HF','etiology','NIC','orientation','l','channel_wga','3','channel_asma','2','channel_vim','4'}
    {'200102_1_overview','group','HF','etiology','IC','orientation','l','channel_wga','3','channel_asma','4','channel_vim','2'}
    {'200106_2_overview','group','HF','etiology','IC','orientation','l','channel_wga','3','channel_asma','2','channel_vim','4'}
    {'200214_1_overview','group','HF','etiology','IC','orientation','l','channel_wga','2','channel_asma','','channel_vim',''}
    {'200219_1_overview','group','HF','etiology','IC','orientation','l','channel_wga','2','channel_asma','','channel_vim',''}
    {'200318_2_overview','group','HF','etiology','IC','orientation','l','channel_wga','3','channel_asma','2','channel_vim','4'}
    
    {'191206_3_overview','group','Donor','orientation','l','channel_wga','3','channel_asma','4','channel_vim','2'}
    {'200502_2_overview','group','Donor','orientation','l','channel_wga','3','channel_asma','5','channel_vim','4'}
    {'191114_3_overview','group','Donor','orientation','l','channel_wga','3','channel_asma','4','channel_vim','5'}
    {'191125_1_overview','group','Donor','orientation','l','channel_wga','3','channel_asma','4','channel_vim','2'}
    {'201125_1_overview','group','Donor','orientation','l','channel_wga','3','channel_asma','5','channel_vim','4'}
    };

sizeimages=size(images, 1);
%%
fractions = {};

% fractions = load('fractionsFromOverviewAnalysis13-Mar-2021_50um.mat');
% fractions = fractions.fractions;
%
ln = length(fractions);

%%
%generate mask from coordinates generated in fiji, threshold  and calculate mean %area within mask. Divide mask into 100 micron squares.
% Calculate mean % area within sub masks. Store results in cell array


idx = ln;

for i=13:13%1:sizeimages
    imagename=images{i}{1};
    if(ln~=0)
        if (ismember(imagename, fractions(1,:)))
            continue
        end
    end
    idx = idx+1;
    fractions{1,idx} = imagename;
    I = ci_loadLif(['Images/' imagename '.lif']); %load the image
    
    orient = readcell('orientationStack.txt');
    loc = find(contains(orient(:,1),imagename(1:8)));
    angle = orient{loc,2};
    
    fileID = fopen(['ROIvalues/' imagename '.txt'],'r');%load the roi used for analysis of fibrosis
    size_cord = [2 Inf];
    cord =fscanf(fileID,'%d %d',size_cord );
    cord =cord';
    numPix = 132; %132 50 µm, 264 100µm, 528 200µm
    %determines mesh resolution and sub image size
    xLim = [cord(1,1) cord(2,1)];
    yLim = [cord(1,2) cord(3,2)];
    sz = [yLim(2)-yLim(1), xLim(2)-xLim(1)];
    xLim(2) = xLim(2)-1;
    yLim(2) = yLim(2)-1;
    
    %load channels of the image and correct orientation
    
    %wga
    if exist('wga','var') clearvars wga; end
    k=strfind(images{i},'channel_wga');
    loc= find(~cellfun(@isempty,k));
    wga=cell2mat(I.Image(str2num(images{i}{loc+1})));
    wga= double(wga);
    wga=flipud(wga);
    wga= imrotate(wga,-90,'bilinear');
    wga= imrotate(wga,-angle,'bilinear','crop');
    wga = wga(yLim(1):yLim(2),xLim(1):xLim(2));
    
    %dapi
    if exist('dapi','var') clearvars dapi; end
    dapi=cell2mat(I.Image(1));
    dapi= double(dapi);
    dapi=flipud(dapi);
    dapi= imrotate(dapi,-90,'bilinear');
    dapi = imrotate(dapi,-angle,'bilinear','crop');
    dapi = dapi(yLim(1):yLim(2),xLim(1):xLim(2))  ;
    %vim
    if exist('vim','var') clearvars vim; end
    k=strfind(images{i},'channel_vim');
    loc= find(~cellfun(@isempty,k));
    if (~isempty(images{i}{loc+1}))
        vim=cell2mat(I.Image(str2num(images{i}{loc+1})));
        vim= double(vim);
        vim=flipud(vim);
        vim= imrotate(vim,-90,'bilinear');
        vim =imrotate(vim,-angle,'bilinear','crop');
        vim = vim(yLim(1):yLim(2),xLim(1):xLim(2));
    end
    
    %asma
    if exist('asma','var') clearvars asma; end
    k=strfind(images{i},'channel_asma');
    loc= find(~cellfun(@isempty,k));
    if (~isempty(images{i}{loc+1}))
        asma=cell2mat(I.Image(str2num(images{i}{loc+1})));
        asma= double(asma);
        asma=flipud(asma);
        asma= imrotate(asma,-90, 'bilinear');
        asma = imrotate(asma,-angle,'bilinear','crop');
        asma= asma(yLim(1):yLim(2),xLim(1):xLim(2));
    end
    
    %indicate group name for each image
    k=strfind(images{i},'group');
    loc= find(~cellfun(@isempty,k));
    fractions{2,idx} = (images{i}{loc+1});
    
    %dapi processing
    %thresholded dapi roi
    [~, dapi_th] = getMaskValue(dapi,2);
    %get image within bounding box of roi
    
    se = strel('disk',1,0);
    dapi_open = imopen(dapi_th,se);
    dapi_to = logical(dapi_open);
    %include only CC having pixel count less than 3000
    dapi_cleaned = bwpropfilt(dapi_to,'Area',[0 3000]);
    
    % get overall value of 3 channels within mask
    overall= zeros(1,4);
    
    [~, wga_th] = getMaskValue(wga,1);
    %read mask for 100% ecm fraction
    maskImage = ['Masks/' imagename(1:end-8) 'Mask.tif'];
    if(exist(maskImage))
        maskECM = imread(maskImage);
        input= wga_th;
        input(maskECM==1) = 1;
    else input =wga_th;
    end
    
    overall(1,1) = mean(input,'all')*100; %total fibrosis
    
    if exist('asma', 'var')
        
        %thresholded asma roi
        [~, asma_th] = getMaskValue(asma,3);
        asma_open= imopen(asma_th,se);
        asma_to = logical(asma_open);
        %only include connected component having pixels less than 1000
        asma_cleaned= bwpropfilt(asma_to,'Area',[0 1000]);
        
        %distance map of asma
        dist_asma = bwdist(asma_cleaned);
        dist_myofib = zeros(size(dist_asma));
        %select regions of dapi within 1 pixel (380 nm) of asma signal
        dist_myofib(dist_asma<=1) =1;
        %
        dapi_myofib = dist_myofib.* double(dapi_cleaned);
        
        %add resulting asma and dapi
        
        myofib = dapi_myofib + asma_cleaned;
        myofib(myofib>1) = 1;
        myofib(~input) = 0;
    else
        overall(1,2)=nan;
    end
    
    if exist('vim', 'var')
        %thresholded vimentin roi
        [~, vim_th] = getMaskValue(vim,2.5);
        
        vim_open = imopen(vim_th,se);
        vim_to = logical(vim_open);
        %only include connected component having pixels less than 1000
        vim_cleaned= bwpropfilt(vim_to,'Area',[0 1000]);
        
        
        %distance map of vimentin
        dist_vim = bwdist(vim_cleaned);
        dist_fib = zeros(size(dist_vim));
        %select regions of dapi within 1 pixel of vimentin signal
        dist_fib(dist_vim<=1) =1;
        dapi_fib = dist_fib.* double(dapi_cleaned);
        
        %add resulting vimentin and dapi
        fib = dapi_fib + vim_cleaned;
        fib(fib>1) = 1;
        fib(~input)=0;
        %allocate overlapping fibroblast myofibroblast regions to only
        %myofibroblasts
        fib(myofib==1) =0;
        
        overall(1,2) = mean(myofib,'all') *100;
        overall(1,3) = mean(fib,'all') *100;
    else
        overall(1,3) =nan;
    end
    
    if isnan(overall(1,2))
        overall(1,4) = overall(1,1);
    else overall(1,4) = overall(1,1) - (overall(1,2)+overall(1,3));
    end
    
    fractions{3,idx} = overall;
    %         f=figure(); imagesc(input); colormap(gray); hold on;
    %split mask into squares
    count=0;
    sizeX = floor(sz(2)/numPix);
    sizeY = floor(sz(1)/numPix);
    subFractions = zeros(sizeX*sizeY,4);
    startX=1;startY=1;
    for x = 1:sizeX
        for y =1:sizeY
            a= startY; b= startY+numPix-1; c= startX; d= startX+numPix-1;
            if (d<=sz(2) && b<=sz(1))
                count=count+1;
                subFractions(count,1) = mean(input(a:b,c:d),'all')*100;
                if exist('asma', 'var')
                    subFractions(count,2) = mean(myofib(a:b,c:d),'all')*100;
                end
                if exist('vim', 'var')
                    subFractions(count,3) = mean(fib(a:b,c:d),'all')*100;
                end
                
            end
            startY = startY+numPix;
        end
        startX= startX+numPix;
        startY = 1;
    end
    subFractions(:,4) = subFractions(:,1)-subFractions(:,2)-subFractions(:,3);
    sumFMF = subFractions(:,2)+subFractions(:,3);
    
    ECM = reshape(subFractions(:,4),sizeY,sizeX);
    FMF = reshape(sumFMF,sizeY,sizeX);
    folder = ['meshForSim' num2str(numPix/2640) 'mm'];
    if ~exist(folder,'dir') 
        mkdir(folder) 
    end
    save([folder '/' imagename(1:8) '_ECM'],'ECM');
    save([folder '/' imagename(1:8) '_FMF'],'FMF');
    
    fractions{4,idx} = subFractions;
    
end

%% Adding relevant clinical variable
for i = 1: length(images)
    
    k=strfind(images{i},'etiology');
    loc= find(~cellfun(@isempty,k));
    if ~isempty(loc)
        fractions{7,idx} = (images{i}{loc+1});
    end
end

%% sorting HF and donors
newFractions = fractions';
newFractions = sortrows(newFractions,2,'descend');
fractions = newFractions';

save(['fractionsFromOverviewAnalysis' date num2str(numPix/2640) 'mm.mat'], 'fractions');

%% Data wrangling

% grouping for analysis
sizeFractions = size(fractions);
allOverview = zeros(sizeFractions(1,2),1);
wgaOverview = zeros(sizeFractions(1,2),1);
asmaOverview = zeros(sizeFractions(1,2),1);
vimOverview = zeros(sizeFractions(1,2),1);
group={};
groupSub =strings;
etiology={};
allSub = [];
wgaSub =[];
vimSub=[];
asmaSub = [];
for i=1:sizeFractions(1,2)
    allOverview(i,1) = fractions{3,i}(1,1);
    wgaOverview(i,1) = fractions{3,i}(1,4);
    asmaOverview(i,1) = fractions{3,i}(1,2);
    vimOverview(i,1) = fractions{3,i}(1,3);
    group{i,1} = fractions{2,i};
    etiology{i,1} = fractions{7,i};
    lBegin = length(wgaSub);
    allSub = [allSub; fractions{4,i}(:,1)];
    wgaSub = [wgaSub; fractions{4,i}(:,4)];
    vimSub = [vimSub; fractions{4,i}(:,3)];
    asmaSub = [asmaSub; fractions{4,i}(:,2)];
    lEnd = length(wgaSub);
    for count = lBegin+1:lEnd
        groupSub(count)= string(fractions{1,i});
    end
end
% asmaOverview = rmmissing(asmaOverview); %2 HF do not have vim and asma
% vimOverview = rmmissing(vimOverview);
fmfOverview = asmaOverview + vimOverview;

B = categorical(group);
groupCat = reordercats(B,{'Donor','HF'});
groupTypes = categories(groupCat);

values = [1,2];

[found, where] = ismember(group, groupTypes);
groupNum = nan(size(group));
groupNum(found) = values(where(found));

etiologyArray = etiology;
etiologyArray(cellfun(@isempty,etiology))={'Donor'};
etiologyCat = categorical(etiologyArray);
etiologies = categories( etiologyCat);
%% Stats

% mean , SE and sd of the overview of 3 signals
[wgaOverviewMean,wgaOverviewSE, wgaOverviewSD] = grpstats(wgaOverview,group,{'mean','sem','std'});
[vimOverviewMean, vimOverviewSE, vimOverviewSD] = grpstats(vimOverview,group,{'mean','sem','std'});
[asmaOverviewMean, asmaOverviewSE, asmaOverviewSD] = grpstats(asmaOverview,group,{'mean','sem','std'});
[fmfOverviewMean, fmfOverviewSE, fmfOverviewSD] = grpstats(fmfOverview,group,{'mean','sem','std'});
[allOverviewMean,allOverviewSE, allOverviewSD] = grpstats(allOverview,group,{'mean','sem','std'});
fibrosis = allOverview - allOverviewMean(2);

% mean and sd of sd of subimages of 3 signals
[wgaSubMean, wgaSubSE, wgaSubSD] = grpstats(wgaSub,groupSub,{'mean','sem','std'});
MeanSD_wgaSub = mean(wgaSubSD);
DevSD_wgaSub = std(wgaSubSD);
[wgaSubSDMean, wgaSubSDSD] = grpstats(wgaSubSD, group,{'mean','std'});

[vimSubMean, vimSubSE, vimSubSD] = grpstats(vimSub,groupSub,{'mean','sem','std'});
MeanSD_vimSub = mean(vimSubSD);
DevSD_vimSub = std(vimSubSD);
[vimSubSDMean, vimSubSDSD] = grpstats(vimSubSD, group,{'mean','std'});


[asmaSubMean, asmaSubSE, asmaSubSD] = grpstats(asmaSub,groupSub,{'mean','sem','std'});
MeanSD_asmaSub = mean(asmaSubSD);
DevSD_asmaSub = std(asmaSubSD);
[asmaSubSDMean, asmaSubSDSD] = grpstats(asmaSubSD, group,{'mean','std'});

[allSubMean, allSubSE, allSubSD] = grpstats(allSub,groupSub,{'mean','sem','std'});
MeanSD_allSub = mean(allSubSD);
DevSD_allSub = std(allSubSD);
[allSubSDMean, allSubSDSD] = grpstats(allSubSD, group,{'mean','std'});
%% significance between HF and donor
HvsD = table;
varias = {'wgaOverview', 'asmaOverview','vimOverview','fmfOverview',...
    'allOverview','fibrosis','allSubSD'};
for n = 1:7
    var= eval(varias{n});
    [h,p] = ttest2(var(groupCat == 'HF'), var(groupCat == 'Donor'),'Vartype','unequal');
    HvsD.h(varias{n})= h;
    HvsD.p(varias{n})= p;
end
HvsD.Row = varias;

%% Extra Analyses

%analysis based on tissue orientation

orientation = {};
idx=1;
for n=1:size(images, 1)
    imagename=images{n}{1};
    
    if (ismember(imagename, fractions(1,:)))
        k=strfind(images{n},'orientation');
        loc= find(~cellfun(@isempty,k));
        if ~isempty(loc)
            orientation{idx}= (images{n}{loc+1});
            idx=idx+1;
        else
            continue
        end
        
    end
end
count = zeros(2,1);
orientationHF = orientation(groupCat=='HF');
types = {'o','l'};
for n=1:2
    k= strfind(orientationHF,types{n});
    count(n) = sum(~cellfun(@isempty,k));
end

[h,p] = ttest2(allOverview(groupCat=='HF'& orientationCat=='l'),wgaOverview(groupCat=='HF'& orientationCat=='o'),'Vartype','unequal')
%% table form of fractions

ft = cell2table(fractions','VariableNames',{'Name' 'Group' 'Overview' ...
    'subFractions' 'Gender' 'LVEF' 'Etiology' 'HFDuration' 'Age' });

%% etiology with donor anova

[p,tbl,stats] = anova1(allOverview, etiologyCat);
[c,m,h,gnames] = multcompare(stats);
compDICNIC=cell2table([gnames(c(:,1)), gnames(c(:,2)), num2cell(c(:,3:6))],...
    'VariableNames',{'pair1', 'pair2', 'lCI95', 'meandiff', 'uCI95','p-value'});

[p,tbl,stats] = anova1(allSubSD, etiologyCat);
[c,m,h,gnames] = multcompare(stats);
compSubDICNIC=cell2table([gnames(c(:,1)), gnames(c(:,2)), num2cell(c(:,3:6))],...
    'VariableNames',{'pair1', 'pair2', 'lCI95', 'meandiff', 'uCI95','p-value'});




%% significance between IC and NIC
ICvsNIC = table;
varias = {'wgaOverview', 'asmaOverview','vimOverview','fmfOverview',...
    'allOverview','allSubSD'};
for n = 1:6
    var= eval(varias{n});
    [h,p] = ttest2(var(strcmp(ft.Etiology,'IC')), var((strcmp(ft.Etiology,'NIC'))));%,'Vartype','unequal');
    ICvsNIC.h(varias{n})= h;
    ICvsNIC.p(varias{n})= p;
end
ICvsNIC.Row = varias;
%% function for thresholding by  mode + f_sd * sd

function [result,image_th] = getMaskValue(image,fsd)

m= mode(reshape(image,1,[]));
sd = std(reshape(image,1,[]));
thresh= m+(fsd*sd);
image_th = image;
image_th(image_th<thresh)=0;
image_th(image_th>=thresh)=1;
result = mean(image_th,'all')*100;

end


